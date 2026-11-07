#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="${HOME}/.config/herdr-telegram"
OS="$(uname -s)"

echo "=== Herdr Telegram Bridge Installer (${OS}) ==="

# 1. Prerequisite checks
PYTHON_BIN="$(command -v python3 || command -v python || true)"
if [ -z "${PYTHON_BIN}" ]; then
    echo "[-] Error: python3 is required but not installed." >&2
    exit 1
fi

if ! command -v herdr >/dev/null 2>&1 && [ ! -f "${HOME}/.local/bin/herdr" ]; then
    echo "[!] Warning: 'herdr' was not found in PATH or ~/.local/bin."
    echo "    Make sure Herdr is installed before running the bridge."
fi

# 2. Setup config directory
echo "[+] Setting up config directory in ${CONFIG_DIR}..."
mkdir -p "${CONFIG_DIR}"

echo "[+] Installing bot package and scripts..."
cp -rf "${SCRIPT_DIR}/src/"* "${CONFIG_DIR}/"
chmod +x "${CONFIG_DIR}/bot.py"

if [ -d "${SCRIPT_DIR}/web/dist" ]; then
    echo "[+] Installing Telegram Mini App assets..."
    mkdir -p "${CONFIG_DIR}/web"
    cp -rf "${SCRIPT_DIR}/web/dist" "${CONFIG_DIR}/web/"
fi

CONFIG_IS_NEW=0
if [ ! -f "${CONFIG_DIR}/config.json" ]; then
    echo "[+] Creating initial config template in ${CONFIG_DIR}/config.json..."
    cp "${SCRIPT_DIR}/config.example.json" "${CONFIG_DIR}/config.json"
    CONFIG_IS_NEW=1
else
    echo "[*] Existing config found at ${CONFIG_DIR}/config.json (preserving)."
fi

# 3. Platform-specific service installation
case "${OS}" in
    Linux*)
        echo "[+] Detected Linux. Installing systemd user service..."
        SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"
        mkdir -p "${SYSTEMD_USER_DIR}"
        cp -f "${SCRIPT_DIR}/systemd/herdr-telegram.service" "${SYSTEMD_USER_DIR}/herdr-telegram.service"
        
        echo "[+] Reloading systemd user daemon..."
        systemctl --user daemon-reload
        
        if command -v loginctl >/dev/null 2>&1; then
            echo "[+] Enabling user linger for ${USER}..."
            loginctl enable-linger "${USER}" 2>/dev/null || true
        fi

        echo ""
        echo "=== Linux Installation Complete ==="
        if [ "${CONFIG_IS_NEW}" -eq 1 ]; then
            echo "[!] Edit ${CONFIG_DIR}/config.json with your Telegram credentials, then run:"
            echo "    systemctl --user enable --now herdr-telegram.service"
        else
            echo "[+] Starting / restarting service..."
            systemctl --user enable --now herdr-telegram.service
            echo "[+] Status: $(systemctl --user is-active herdr-telegram.service)"
            echo "    View live logs with: journalctl --user -u herdr-telegram.service -f"
        fi
        ;;

    Darwin*)
        echo "[+] Detected macOS. Installing launchd user agent..."
        LAUNCHD_DIR="${HOME}/Library/LaunchAgents"
        mkdir -p "${LAUNCHD_DIR}"
        PLIST_FILE="${LAUNCHD_DIR}/com.herdr.telegram.plist"

        # Stop existing agent if running
        launchctl unload "${PLIST_FILE}" 2>/dev/null || true

        # Generate plist with real absolute paths
        sed -e "s|__PYTHON_BIN__|${PYTHON_BIN}|g" \
            -e "s|__BOT_SCRIPT__|${CONFIG_DIR}/bot.py|g" \
            -e "s|__CONFIG_DIR__|${CONFIG_DIR}|g" \
            -e "s|__USER_HOME__|${HOME}|g" \
            "${SCRIPT_DIR}/launchd/com.herdr.telegram.plist" > "${PLIST_FILE}"

        echo ""
        echo "=== macOS Installation Complete ==="
        if [ "${CONFIG_IS_NEW}" -eq 1 ]; then
            echo "[!] Edit ${CONFIG_DIR}/config.json with your Telegram credentials, then run:"
            echo "    launchctl load -w ${PLIST_FILE}"
        else
            echo "[+] Loading launchd agent..."
            launchctl load -w "${PLIST_FILE}"
            echo "[+] Agent loaded. Logs available in ${CONFIG_DIR}/bot.log and ${CONFIG_DIR}/bot.err.log"
        fi
        ;;

    MINGW*|MSYS*|CYGWIN*)
        echo "[!] Detected Windows bash environment."
        echo "    For native Windows execution, run install.ps1 from PowerShell:"
        echo "    powershell -ExecutionPolicy Bypass -File .\\install.ps1"
        ;;

    *)
        echo "[-] Unsupported operating system: ${OS}" >&2
        exit 1
        ;;
esac
