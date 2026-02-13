# nstr-report

Daily BNOC (Bitcoin Network Operations Collective) activity summary bot for Nostr.

## Features

- Fetches daily activity from [bnoc.xyz](https://bnoc.xyz)
- Generates AI-powered summaries using Claude API
- Publishes to Nostr relays
- Runs as a systemd timer service
- Stores keys securely in `~/.nstr-report`

## Installation

```bash
./install.sh
```

## Usage

```bash
# Test without publishing
nstr-report --dry-run

# Publish to Nostr
nstr-report

# Update profile metadata
nstr-report --update-profile

# Show configuration
nstr-report --show-config
```

## Configuration

Configuration is stored in `~/.nstr-report` (JSON format):

```json
{
  "nostr": {
    "private_key_hex": "..."
  },
  "relays": {
    "urls": [
      "wss://relay.damus.io",
      "wss://relay.primal.net",
      "wss://nos.lol",
      "wss://relay.bitcoindistrict.org"
    ]
  },
  "source": {
    "url": "https://bnoc.xyz",
    "lookback_hours": 24
  },
  "anthropic": {
    "api_key": "sk-ant-..."
  }
}
```

## Systemd Timer

Enable daily reports:

```bash
systemctl --user enable --now nstr-report.timer
```

Check status:

```bash
systemctl --user status nstr-report.timer
journalctl --user -u nstr-report
```

## Output

If activity found:
```
BNOC Daily Summary (2026-02-12)

2 topics with activity:

  Attack on I2P: Bitcoin nodes not reachable via I2P [p2p, i2p] (b10c)
    https://bnoc.xyz/t/attack-on-i2p-bitcoin-nodes-not-reachable-via-i2p/79

Summary:
Discussion on ongoing I2P network attack affecting Bitcoin node connectivity.

Source: https://bnoc.xyz
```

If no activity:
```
NSTR - Nothing Significant to Report
```
