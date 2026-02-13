"""Main entry point for nstr-report."""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .config import load_config, CONFIG_PATH
from .fetcher import fetch_activity
from .formatter import format_activity
from .nostr import publish_note, get_public_key, fetch_latest_note

# Cache file for daily summary
CACHE_PATH = Path.home() / ".cache" / "nstr-report" / "daily.json"


def save_cache(message: str, date: str) -> None:
    """Save the daily summary to cache."""
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {"message": message, "date": date, "posted_at": []}
    CACHE_PATH.write_text(json.dumps(data, indent=2))


def load_cache() -> dict | None:
    """Load the cached daily summary."""
    if not CACHE_PATH.exists():
        return None
    try:
        return json.loads(CACHE_PATH.read_text())
    except Exception:
        return None


def update_cache_posted(timestamp: str) -> None:
    """Record that we posted the cached summary."""
    cache = load_cache()
    if cache:
        cache.setdefault("posted_at", []).append(timestamp)
        CACHE_PATH.write_text(json.dumps(cache, indent=2))


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Fetch BNOC activity and publish to Nostr"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the message without publishing to Nostr",
    )
    parser.add_argument(
        "--update-profile",
        action="store_true",
        help="Update the Nostr profile metadata",
    )
    parser.add_argument(
        "--show-config",
        action="store_true",
        help="Show configuration and exit",
    )
    parser.add_argument(
        "--repost",
        action="store_true",
        help="Repost the cached daily summary (don't fetch new data)",
    )

    args = parser.parse_args()

    # Load configuration
    config = load_config()

    if args.show_config:
        print(f"Config file: {CONFIG_PATH}")
        print(f"Cache file: {CACHE_PATH}")
        if config.bunker_uri:
            print(f"Signer: Remote (NIP-46 bunker)")
            print(f"Bunker URI: {config.bunker_uri[:50]}...")
        elif config.private_key_hex:
            print(f"Signer: Local keys")
            print(f"Public key: {get_public_key(config.private_key_hex)}")
        else:
            print("Signer: NOT CONFIGURED")
            print("  Add 'bunker_uri' or 'private_key_hex' to config")
        print(f"Source URL: {config.source_url}")
        print(f"Lookback hours: {config.lookback_hours}")
        print(f"Relays: {', '.join(config.relays)}")
        print(f"Anthropic API key: {'set' if config.anthropic_api_key else 'not set'}")
        
        # Show cache info
        cache = load_cache()
        if cache:
            print(f"Cached summary date: {cache.get('date', 'unknown')}")
            print(f"Times posted: {len(cache.get('posted_at', []))}")
        else:
            print("Cached summary: none")
        return 0

    # Check signer is configured
    if not config.bunker_uri and not config.private_key_hex:
        print("Error: No signer configured", file=sys.stderr)
        print(f"Edit {CONFIG_PATH} and add either:", file=sys.stderr)
        print('  "bunker_uri": "bunker://..." (recommended)', file=sys.stderr)
        print('  "private_key_hex": "..."', file=sys.stderr)
        return 1

    # Track AI failure for angry notification
    ai_error_message = None

    # Handle repost mode
    if args.repost:
        cache = load_cache()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        # Try cache first
        if cache and cache.get("date") == today:
            message = cache["message"]
            print(f"Reposting cached summary from {cache['date']}...")
        else:
            # Cache miss or stale - try fetching from Nostr
            print("Cache miss or stale, fetching latest note from Nostr...")
            npub = get_public_key(config.private_key_hex) if config.private_key_hex else None
            
            if npub:
                try:
                    latest = fetch_latest_note(npub, config.relays, contains="BNOC Daily Summary")
                    if latest:
                        message = latest
                        print("Found latest summary on Nostr, reposting...")
                        # Save to cache for next time
                        save_cache(message, today)
                    else:
                        print("No valid summary found on Nostr.", file=sys.stderr)
                        print("Run without --repost to generate today's summary.", file=sys.stderr)
                        return 1
                except Exception as e:
                    print(f"Error fetching from Nostr: {e}", file=sys.stderr)
                    print("Run without --repost to generate today's summary.", file=sys.stderr)
                    return 1
            else:
                print("No cached summary and cannot query Nostr without pubkey.", file=sys.stderr)
                return 1
        
        if args.dry_run:
            print("\n--- Cached Message (dry run) ---")
            print(message)
            print("--- End message ---\n")
            return 0
    else:
        # Fetch activity and generate new summary
        print(f"Fetching activity from {config.source_url}...")
        try:
            activity = fetch_activity(config.source_url, config.lookback_hours)
        except Exception as e:
            print(f"Error fetching activity: {e}", file=sys.stderr)
            return 1

        print(f"Found {len(activity.topics)} topics with activity")

        # Format the message
        output = format_activity(activity, config.anthropic_api_key)
        message = output.message
        
        if output.ai_failed:
            ai_error_message = output.error_message

        if args.dry_run:
            print("\n--- Message (dry run) ---")
            print(message)
            if ai_error_message:
                print("\n--- AI FAILED - Would also post: ---")
                print(ai_error_message)
            print("--- End message ---\n")
            return 0

        # Save to cache
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        save_cache(message, today)
        print(f"Saved summary to cache for {today}")

    # Publish to Nostr
    print(f"Publishing to {len(config.relays)} relays: {', '.join(config.relays)}")
    try:
        event_id = publish_note(
            content=message,
            relays=config.relays,
            private_key_hex=config.private_key_hex,
            bunker_uri=config.bunker_uri,
            app_key_hex=config.app_key_hex,
            update_profile=args.update_profile,
        )
        print(f"Published! Event ID: {event_id}")
        if config.private_key_hex:
            npub = get_public_key(config.private_key_hex)
            print(f"View at: https://njump.me/{npub}")
        
        # Record the post time
        update_cache_posted(datetime.now(timezone.utc).isoformat())
        
        # If AI failed (only on fresh generate), post angry notification
        if ai_error_message:
            print("AI failed - posting angry notification...")
            try:
                angry_event_id = publish_note(
                    content=ai_error_message,
                    relays=config.relays,
                    private_key_hex=config.private_key_hex,
                    bunker_uri=config.bunker_uri,
                    app_key_hex=config.app_key_hex,
                    update_profile=False,
                )
                print(f"Angry notification posted! Event ID: {angry_event_id}")
            except Exception as e:
                print(f"Warning: Could not post angry notification: {e}", file=sys.stderr)
                
    except Exception as e:
        print(f"Error publishing to Nostr: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
