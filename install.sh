#!/bin/bash
set -euo pipefail

# nstr-report installer
# Installs the daemon as a user systemd service

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"

echo "=== nstr-report installer ==="
echo

# Check for Python 3.10+
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is required but not found"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
if [[ "$(echo "$PYTHON_VERSION < 3.10" | bc -l)" -eq 1 ]]; then
    echo "Error: Python 3.10+ required, found $PYTHON_VERSION"
    exit 1
fi

echo "Using Python $PYTHON_VERSION"

# Install the package
echo "Installing nstr-report..."
pip install --user -e "$SCRIPT_DIR"

# Verify installation
if ! command -v nstr-report &> /dev/null; then
    echo "Warning: nstr-report not found in PATH"
    echo "You may need to add ~/.local/bin to your PATH"
    export PATH="$HOME/.local/bin:$PATH"
fi

# Create systemd user directory if needed
mkdir -p "$SYSTEMD_USER_DIR"

# Install systemd units
echo "Installing systemd units..."
cp "$SCRIPT_DIR/systemd/nstr-report.service" "$SYSTEMD_USER_DIR/"
cp "$SCRIPT_DIR/systemd/nstr-report.timer" "$SYSTEMD_USER_DIR/"

# Reload systemd
systemctl --user daemon-reload

# Initialize configuration (creates keys if needed)
echo "Initializing configuration..."
nstr-report --show-config

# Create env file directory for systemd
mkdir -p "$HOME/.config/nstr-report"

echo
echo "=== Installation complete ==="
echo
echo "To enable the daily timer:"
echo "  systemctl --user enable --now nstr-report.timer"
echo
echo "To run manually:"
echo "  nstr-report --dry-run    # Test without publishing"
echo "  nstr-report              # Publish to Nostr"
echo
echo "To set your Anthropic API key for AI summaries:"
echo "  echo 'ANTHROPIC_API_KEY=sk-ant-...' > ~/.config/nstr-report/env"
echo
echo "Or add to ~/.nstr-report:"
echo '  "anthropic": {"api_key": "sk-ant-..."}'
