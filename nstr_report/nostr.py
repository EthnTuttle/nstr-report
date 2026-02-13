"""Nostr key management and publishing."""

import asyncio
from nostr_sdk import (
    Keys,
    Client,
    EventBuilder,
    Filter,
    Kind,
    Metadata,
    MetadataRecord,
    SecretKey,
    NostrSigner,
    NostrConnect,
    NostrConnectUri,
    PublicKey,
    RelayUrl,
)
from datetime import timedelta


PROFILE_NAME = "nstr-report"
PROFILE_BIO = "NSTR - Nothing Significant to Report. Daily summaries of Bitcoin Network Operations Collective (bnoc.xyz) activity."

# Retry settings
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 5


def get_keys(private_key_hex: str) -> Keys:
    """Get Keys object from hex private key."""
    secret_key = SecretKey.parse(private_key_hex)
    return Keys(secret_key)


async def create_signer(
    private_key_hex: str | None = None,
    bunker_uri: str | None = None,
    app_key_hex: str | None = None,
) -> NostrSigner:
    """Create a NostrSigner from either local keys or bunker URI.

    Args:
        private_key_hex: Local private key (hex) - used if bunker_uri not set
        bunker_uri: NIP-46 bunker URI for remote signing
        app_key_hex: App keys for bunker connection (generated if not provided)

    Returns:
        NostrSigner instance
    """
    if bunker_uri:
        # Remote signing via NIP-46
        uri = NostrConnectUri.parse(bunker_uri)

        # App keys for the connection (not the signing keys)
        if app_key_hex:
            app_keys = get_keys(app_key_hex)
        else:
            app_keys = Keys.generate()

        timeout = timedelta(seconds=60)
        connect = NostrConnect(uri, app_keys, timeout, None)

        return NostrSigner.nostr_connect(connect)
    elif private_key_hex:
        # Local signing
        keys = get_keys(private_key_hex)
        return NostrSigner.keys(keys)
    else:
        raise ValueError("Either private_key_hex or bunker_uri must be provided")


async def publish_note_async(
    content: str,
    relays: list[str],
    private_key_hex: str | None = None,
    bunker_uri: str | None = None,
    app_key_hex: str | None = None,
    update_profile: bool = False,
    max_retries: int = MAX_RETRIES,
) -> str:
    """Publish a note to Nostr relays with retry logic.

    Args:
        content: The note content to publish
        relays: List of relay URLs to publish to
        private_key_hex: Local private key (hex) - used if bunker_uri not set
        bunker_uri: NIP-46 bunker URI for remote signing
        app_key_hex: App keys for bunker connection
        update_profile: Whether to update the profile metadata
        max_retries: Maximum number of retry attempts

    Returns:
        The event ID of the published note

    Raises:
        Exception: If publishing fails after all retries
    """
    last_error = None
    
    for attempt in range(max_retries):
        try:
            signer = await create_signer(private_key_hex, bunker_uri, app_key_hex)
            client = Client(signer)

            # Add relays
            for relay in relays:
                relay_url = RelayUrl.parse(relay)
                await client.add_relay(relay_url)

            # Connect to relays
            await client.connect()
            
            # Wait a moment for connections to establish
            await asyncio.sleep(2)

            # Optionally update profile
            if update_profile:
                record = MetadataRecord(
                    name=PROFILE_NAME,
                    about=PROFILE_BIO,
                )
                metadata = Metadata.from_record(record)
                await client.set_metadata(metadata)

            # Build and publish the note
            builder = EventBuilder.text_note(content)
            output = await client.send_event_builder(builder)

            # Check results
            success_count = len(output.success) if output.success else 0
            failed_count = len(output.failed) if output.failed else 0
            
            print(f"  Attempt {attempt + 1}: {success_count} relays succeeded, {failed_count} failed")
            
            if output.failed:
                for relay_url, error in output.failed.items():
                    print(f"    Failed: {relay_url} - {error}")

            # Disconnect
            await client.disconnect()

            # Success if at least one relay accepted the event
            if success_count > 0:
                return output.id.to_hex()
            
            # All relays failed - will retry
            last_error = f"All {failed_count} relays failed"
            
        except Exception as e:
            last_error = str(e)
            print(f"  Attempt {attempt + 1} failed: {last_error}")
        
        # Wait before retry (except on last attempt)
        if attempt < max_retries - 1:
            print(f"  Retrying in {RETRY_DELAY_SECONDS} seconds...")
            await asyncio.sleep(RETRY_DELAY_SECONDS)
    
    raise Exception(f"Failed to publish after {max_retries} attempts: {last_error}")


def publish_note(
    content: str,
    relays: list[str],
    private_key_hex: str | None = None,
    bunker_uri: str | None = None,
    app_key_hex: str | None = None,
    update_profile: bool = False,
    max_retries: int = MAX_RETRIES,
) -> str:
    """Synchronous wrapper for publish_note_async."""
    return asyncio.run(
        publish_note_async(
            content, relays, private_key_hex, bunker_uri, app_key_hex, 
            update_profile, max_retries
        )
    )


def get_public_key(private_key_hex: str) -> str:
    """Get the public key (npub) for display."""
    keys = get_keys(private_key_hex)
    return keys.public_key().to_bech32()


def get_public_key_hex(private_key_hex: str) -> str:
    """Get the public key as hex for lookups."""
    keys = get_keys(private_key_hex)
    return keys.public_key().to_hex()


async def get_bunker_public_key(bunker_uri: str, app_key_hex: str | None = None) -> str:
    """Get the public key from a bunker URI."""
    uri = NostrConnectUri.parse(bunker_uri)
    if app_key_hex:
        app_keys = get_keys(app_key_hex)
    else:
        app_keys = Keys.generate()

    timeout = timedelta(seconds=60)
    connect = NostrConnect(uri, app_keys, timeout, None)
    pubkey = await connect.get_public_key()
    return pubkey.to_bech32()


async def fetch_latest_note_async(
    pubkey: str,
    relays: list[str],
    contains: str | None = None,
) -> str | None:
    """Fetch the latest text note from a pubkey.

    Args:
        pubkey: Public key (npub or hex)
        relays: List of relay URLs to query
        contains: Optional string that must be in the note content

    Returns:
        Content of the latest matching note, or None if not found
    """
    client = Client()

    # Add relays
    for relay in relays:
        relay_url = RelayUrl.parse(relay)
        await client.add_relay(relay_url)

    await client.connect()
    await asyncio.sleep(2)  # Wait for connections

    # Parse pubkey
    pk = PublicKey.parse(pubkey)

    # Create filter for text notes (kind 1) from this author
    # Fetch more if we need to filter by content
    limit = 20 if contains else 1
    f = Filter().author(pk).kind(Kind(1)).limit(limit)

    # Fetch events
    events = await client.fetch_events(f, timedelta(seconds=15))

    await client.disconnect()

    # Get the latest event content (optionally matching contains)
    if not events.is_empty():
        for event in events.to_vec():
            content = event.content()
            if contains is None or contains in content:
                return content

    return None


def fetch_latest_note(pubkey: str, relays: list[str], contains: str | None = None) -> str | None:
    """Synchronous wrapper for fetch_latest_note_async."""
    return asyncio.run(fetch_latest_note_async(pubkey, relays, contains))
