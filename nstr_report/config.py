"""Configuration management for nstr-report."""

import json
import os
import secrets
from pathlib import Path
from dataclasses import dataclass, field

from nostr_sdk import SecretKey

CONFIG_PATH = Path.home() / ".nstr-report"


def parse_private_key(key: str) -> str:
    """Parse a private key from nsec or hex format to hex.
    
    Args:
        key: Private key in nsec1... or hex format
        
    Returns:
        Private key as hex string
    """
    if key.startswith("nsec"):
        # Decode nsec to hex
        secret_key = SecretKey.parse(key)
        return secret_key.to_hex()
    else:
        # Assume it's already hex
        return key

DEFAULT_RELAYS = [
    "wss://relay.damus.io",
    "wss://relay.primal.net",
    "wss://nos.lol",
    "wss://relay.bitcoindistrict.org",
]

DEFAULT_SOURCE_URL = "https://bnoc.xyz"
DEFAULT_LOOKBACK_HOURS = 24


@dataclass
class Config:
    """Configuration for nstr-report."""

    relays: list[str] = field(default_factory=lambda: DEFAULT_RELAYS.copy())
    source_url: str = DEFAULT_SOURCE_URL
    lookback_hours: int = DEFAULT_LOOKBACK_HOURS
    anthropic_api_key: str | None = None
    # Local signing (used if bunker_uri not set)
    private_key_hex: str | None = None
    # Remote signing via NIP-46
    bunker_uri: str | None = None
    app_key_hex: str | None = None  # App keys for bunker connection

    def save(self) -> None:
        """Save configuration to dotfile."""
        data = {
            "nostr": {},
            "relays": {
                "urls": self.relays,
            },
            "source": {
                "url": self.source_url,
                "lookback_hours": self.lookback_hours,
            },
        }

        if self.bunker_uri:
            data["nostr"]["bunker_uri"] = self.bunker_uri
            if self.app_key_hex:
                data["nostr"]["app_key_hex"] = self.app_key_hex
        elif self.private_key_hex:
            data["nostr"]["private_key_hex"] = self.private_key_hex

        if self.anthropic_api_key:
            data["anthropic"] = {"api_key": self.anthropic_api_key}

        CONFIG_PATH.write_text(json.dumps(data, indent=2))
        CONFIG_PATH.chmod(0o600)  # Secure permissions


def generate_private_key() -> str:
    """Generate a new private key as hex string."""
    return secrets.token_hex(32)


def load_config() -> Config:
    """Load configuration from dotfile, creating if needed."""
    if not CONFIG_PATH.exists():
        # Create new config - no keys yet, user must configure
        config = Config(
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
        )
        config.save()
        print(f"Created new config at {CONFIG_PATH}")
        print("Configure either bunker_uri (recommended) or private_key_hex in the config file")
        return config

    data = json.loads(CONFIG_PATH.read_text())
    nostr_config = data.get("nostr", {})

    # Parse private key (supports both nsec and hex formats)
    raw_private_key = nostr_config.get("private_key_hex") or nostr_config.get("nsec")
    private_key_hex = parse_private_key(raw_private_key) if raw_private_key else None

    return Config(
        relays=data.get("relays", {}).get("urls", DEFAULT_RELAYS.copy()),
        source_url=data.get("source", {}).get("url", DEFAULT_SOURCE_URL),
        lookback_hours=data.get("source", {}).get("lookback_hours", DEFAULT_LOOKBACK_HOURS),
        anthropic_api_key=data.get("anthropic", {}).get("api_key") or os.environ.get("ANTHROPIC_API_KEY"),
        private_key_hex=private_key_hex,
        bunker_uri=nostr_config.get("bunker_uri"),
        app_key_hex=nostr_config.get("app_key_hex"),
    )
