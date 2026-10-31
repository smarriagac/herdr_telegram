#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="${HOME}/.config/herdr-telegram"
SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"

echo "=== Herdr Telegram Bridge Installer ==="

# 1. Prerequisite checks
command -v python3 >/dev/null 2>&1 || {
    echo "[-] Error: python3 is required but not installed." >&2
    exit 1
}

if ! command -v herdr >/dev/null 2>&1 && [ ! -f "${HOME}/.local/bin/herdr" ]; then
    echo "[!] Warning: 'herdr' binary was not found in PATH or ~/.local/bin."
    echo "    Make sure Herdr is installed before starting the service."
fi

# 2. Setup directories
echo "[+] Setting up directories..."
mkdir -p "${CONFIG_DIR}"
mkdir -p "${SYSTEMD_USER_DIR}"

# 3. Install bot script
echo "[+] Installing bot script..."
cp -f "${SCRIPT_DIR}/src/bot.py" "${CONFIG_DIR}/bot.py"
chmod +x "${CONFIG_DIR}/bot.py"

# 4. Handle configuration
if [ ! -f "${CONFIG_DIR}/config.json" ]; then
    echo "[+] Creating initial config template in ${CONFIG_DIR}/config.json..."
    cp "${SCRIPT_DIR}/config.example.json" "${CONFIG_DIR}/config.json"
    CONFIG_IS_NEW=1
else
    echo "[*] Existing config found at ${CONFIG_DIR}/config.json (preserving)."
    CONFIG_IS_NEW=0
fi

# 5. Install systemd service
echo "[+] Installing systemd user service..."
cp -f "${SCRIPT_DIR}/systemd/herdr-telegram.service" "${SYSTEMD_USER_DIR}/herdr-telegram.service"

echo "[+] Reloading systemd user daemon..."
systemctl --user daemon-reload

# 6. Enable lingering so bot continues running when user is logged out
if command -v loginctl >/dev/null 2>&1; then
    echo "[+] Enabling systemd user linger for ${USER}..."
    loginctl enable-linger "${USER}" 2>/dev/null || true
fi

echo ""
echo "=== Installation Complete ==="
if [ "${CONFIG_IS_NEW}" -eq 1 ]; then
    echo "[!] Action required:"
    echo "    1. Edit ${CONFIG_DIR}/config.json with your Telegram Bot Token and Chat/Group ID."
    echo "    2. Start the service with:"
    echo "       systemctl --user enable --now herdr-telegram.service"
else
    echo "[+] Starting / restarting service..."
    systemctl --user enable --now herdr-telegram.service
    echo "[+] Status: $(systemctl --user is-active herdr-telegram.service)"
    echo "    View live logs with: journalctl --user -u herdr-telegram.service -f"
fi
