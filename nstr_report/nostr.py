"""Nostr key management and publishing."""

import asyncio
from nostr_sdk import (
    Keys,
    Client,
    EventBuilder,
    Metadata,
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
) -> str:
    """Publish a note to Nostr relays.

    Args:
        content: The note content to publish
        relays: List of relay URLs to publish to
        private_key_hex: Local private key (hex) - used if bunker_uri not set
        bunker_uri: NIP-46 bunker URI for remote signing
        app_key_hex: App keys for bunker connection
        update_profile: Whether to update the profile metadata

    Returns:
        The event ID of the published note
    """
    signer = await create_signer(private_key_hex, bunker_uri, app_key_hex)
    client = Client(signer)

    # Add relays
    for relay in relays:
        relay_url = RelayUrl.parse(relay)
        await client.add_relay(relay_url)

    # Connect to relays
    await client.connect()

    # Optionally update profile
    if update_profile:
        metadata = Metadata()
        metadata = metadata.set_name(PROFILE_NAME)
        metadata = metadata.set_about(PROFILE_BIO)
        await client.set_metadata(metadata)

    # Build and publish the note
    builder = EventBuilder.text_note(content)
    output = await client.send_event_builder(builder)

    # Disconnect
    await client.disconnect()

    return output.id.to_hex()


def publish_note(
    content: str,
    relays: list[str],
    private_key_hex: str | None = None,
    bunker_uri: str | None = None,
    app_key_hex: str | None = None,
    update_profile: bool = False,
) -> str:
    """Synchronous wrapper for publish_note_async."""
    return asyncio.run(
        publish_note_async(
            content, relays, private_key_hex, bunker_uri, app_key_hex, update_profile
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
