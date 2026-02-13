"""Main entry point for nstr-report."""

import argparse
import sys

from .config import load_config, CONFIG_PATH
from .fetcher import fetch_activity
from .formatter import format_activity
from .nostr import publish_note, get_public_key


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

    args = parser.parse_args()

    # Load configuration
    config = load_config()

    if args.show_config:
        print(f"Config file: {CONFIG_PATH}")
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
        return 0

    # Check signer is configured
    if not config.bunker_uri and not config.private_key_hex:
        print("Error: No signer configured", file=sys.stderr)
        print(f"Edit {CONFIG_PATH} and add either:", file=sys.stderr)
        print('  "bunker_uri": "bunker://..." (recommended)', file=sys.stderr)
        print('  "private_key_hex": "..."', file=sys.stderr)
        return 1

    # Fetch activity
    print(f"Fetching activity from {config.source_url}...")
    try:
        activity = fetch_activity(config.source_url, config.lookback_hours)
    except Exception as e:
        print(f"Error fetching activity: {e}", file=sys.stderr)
        return 1

    print(f"Found {len(activity.topics)} topics with activity")

    # Format the message
    output = format_activity(activity, config.anthropic_api_key)

    if args.dry_run:
        print("\n--- Message (dry run) ---")
        print(output.message)
        if output.ai_failed:
            print("\n--- AI FAILED - Would also post: ---")
            print(output.error_message)
        print("--- End message ---\n")
        return 0

    # Publish to Nostr
    print(f"Publishing to {len(config.relays)} relays...")
    try:
        event_id = publish_note(
            content=output.message,
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
        
        # If AI failed, also post the angry notification
        if output.ai_failed and output.error_message:
            print("AI failed - posting angry notification...")
            try:
                angry_event_id = publish_note(
                    content=output.error_message,
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
