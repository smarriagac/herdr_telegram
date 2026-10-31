#!/usr/bin/env bash
set -euo pipefail

CONFIG_DIR="${HOME}/.config/herdr-telegram"
SERVICE_FILE="${HOME}/.config/systemd/user/herdr-telegram.service"

echo "=== Herdr Telegram Bridge Uninstaller ==="

echo "[+] Stopping and disabling systemd service..."
systemctl --user stop herdr-telegram.service 2>/dev/null || true
systemctl --user disable herdr-telegram.service 2>/dev/null || true

if [ -f "${SERVICE_FILE}" ]; then
    echo "[+] Removing service file..."
    rm -f "${SERVICE_FILE}"
    systemctl --user daemon-reload
fi

read -rp "Do you want to delete config and topics history in ${CONFIG_DIR}? [y/N]: " CONFIRM
if [[ "${CONFIRM}" =~ ^[Yy]$ ]]; then
    echo "[+] Removing ${CONFIG_DIR}..."
    rm -rf "${CONFIG_DIR}"
else
    echo "[*] Keeping configuration directory: ${CONFIG_DIR}"
fi

echo "=== Uninstallation Complete ==="
