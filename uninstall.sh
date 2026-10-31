#!/usr/bin/env bash
set -euo pipefail

CONFIG_DIR="${HOME}/.config/herdr-telegram"
OS="$(uname -s)"

echo "=== Herdr Telegram Bridge Uninstaller (${OS}) ==="

case "${OS}" in
    Linux*)
        SERVICE_FILE="${HOME}/.config/systemd/user/herdr-telegram.service"
        echo "[+] Stopping and disabling systemd service..."
        systemctl --user stop herdr-telegram.service 2>/dev/null || true
        systemctl --user disable herdr-telegram.service 2>/dev/null || true

        if [ -f "${SERVICE_FILE}" ]; then
            echo "[+] Removing systemd service file..."
            rm -f "${SERVICE_FILE}"
            systemctl --user daemon-reload
        fi
        ;;

    Darwin*)
        PLIST_FILE="${HOME}/Library/LaunchAgents/com.herdr.telegram.plist"
        echo "[+] Unloading launchd agent..."
        launchctl unload "${PLIST_FILE}" 2>/dev/null || true

        if [ -f "${PLIST_FILE}" ]; then
            echo "[+] Removing launchd plist file..."
            rm -f "${PLIST_FILE}"
        fi
        ;;

    *)
        echo "[*] Skipping service removal for ${OS}."
        ;;
esac

read -rp "Do you want to delete configuration and history in ${CONFIG_DIR}? [y/N]: " CONFIRM
if [[ "${CONFIRM}" =~ ^[Yy]$ ]]; then
    echo "[+] Removing ${CONFIG_DIR}..."
    rm -rf "${CONFIG_DIR}"
else
    echo "[*] Keeping configuration directory: ${CONFIG_DIR}"
fi

echo "=== Uninstallation Complete ==="
