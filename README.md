# Herdr Telegram Bridge

A lightweight, zero-dependency bridge between **Telegram** and [Herdr](https://herdr.dev) (the agent-native workspace manager). It allows you to monitor, control, and interact with multiple AI coding agents running on your remote machine directly from your phone.

```mermaid
flowchart LR
    subgraph Telegram["Telegram"]
        Group["Forum Supergroup\n(Topics enabled)"]
        TopicA["#📁 deportivo\n(Topic)"]
        TopicB["#📁 prueba\n(Topic)"]
        Direct["Private Chat\n(Admin)"]
    end

    subgraph Host["Host Machine"]
        Daemon["herdr-telegram-bridge\n(Python Daemon / systemd)"]
        Socket["Herdr Socket API\n(~/.config/herdr/herdr.sock)"]
        
        subgraph Agents["Herdr Workspaces"]
            AgentA["Agent: deportivo\n(agy / claude)"]
            AgentB["Agent: prueba\n(agy / codex)"]
        end
    end

    TopicA <--> Daemon
    TopicB <--> Daemon
    Direct <--> Daemon
    Daemon <--> Socket
    Socket <--> AgentA
    Socket <--> AgentB
```

## Features

- **Zero External Dependencies**: Built entirely using Python's standard library (`urllib`, `subprocess`, `json`, `threading`). No virtual environment or `pip install` required.
- **Isolated Forum Topics**: Automatically manages dedicated Telegram topics for each Herdr workspace. Decisions, notifications, and prompts stay isolated without polluting each other's context.
- **Direct Prompting**: Inside any project topic, typing plain natural language immediately submits a prompt to that agent without requiring `/prompt` commands.
- **Interactive Inline Buttons**: Approve permission requests (`Enter`, `Yes`, `Cancel`), view live terminal outputs, or refresh the status panel with tactile touch controls.
- **Background Persistence**: Runs as an unprivileged `systemd --user` service with user lingering enabled, ensuring agents and the bot remain active even after graphical logout.

---

## Prerequisites

1. **Linux OS** with `systemd`.
2. **Python 3.8+** (`python3`).
3. **Herdr** installed (`~/.local/bin/herdr` or in `PATH`).
4. A **Telegram Bot Token** from [@BotFather](https://t.me/BotFather).

---

## Quick Start / Installation

### 1. Clone the repository
```bash
git clone <repo-url> ~/proyectos/herdr-telegram-bridge
cd ~/proyectos/herdr-telegram-bridge
```

### 2. Run the installer
```bash
./install.sh
```
The installer copies the daemon script to `~/.config/herdr-telegram/bot.py`, installs the systemd unit to `~/.config/systemd/user/herdr-telegram.service`, reloads systemd, and enables lingering (`loginctl enable-linger`).

### 3. Configure credentials
Edit `~/.config/herdr-telegram/config.json`:
```json
{
  "bot_token": "123456789:ABCdefGHIjklMNOpqrSTUvwxYZ",
  "allowed_chat_id": 809438653,
  "group_chat_id": -1004353505956,
  "herdr_bin": "~/.local/bin/herdr",
  "projects_dir": "~/proyectos"
}
```

| Field | Description |
|---|---|
| `bot_token` | HTTP API token obtained from `@BotFather`. |
| `allowed_chat_id` | Your personal Telegram user ID (whitelist security). |
| `group_chat_id` | *(Optional)* The Telegram Supergroup ID with Topics enabled. |
| `herdr_bin` | Path to the `herdr` executable (`herdr` or `~/.local/bin/herdr`). |
| `projects_dir` | Base directory where new projects are created (`~/proyectos`). |

### 4. Enable and start the service
```bash
systemctl --user enable --now herdr-telegram.service
```

Verify service status:
```bash
systemctl --user status herdr-telegram.service
```

View live logs:
```bash
journalctl --user -u herdr-telegram.service -f
```

---

## Telegram Setup (Forum Supergroup)

To enable topic isolation:
1. Create a new Telegram group and add your bot.
2. In the group settings:
   - Enable **Topics** (Modo Foro).
   - Promote your bot to **Administrator** with the **Manage Topics** permission.
3. Send any message in the group. Retrieve the group's `chat_id` (negative integer starting with `-100...`) from the service logs (`journalctl -u herdr-telegram -n 20`).
4. Set `"group_chat_id"` in `config.json` and restart the service (`systemctl --user restart herdr-telegram`).

---

## Commands & Controls

### In Dedicated Project Topics
- **Plain text message**: Directly submits an instruction/prompt to the agent.
- `/read`: Inspects recent terminal output for this agent.
- `/enter`: Sends `Enter` (useful when approving prompts).
- `/yes`: Sends `y` + `Enter`.
- `/esc`: Sends `Escape` to cancel an open dialog.
- `/close`: Closes the Herdr workspace and archives the topic.

### In General Topic or Private Chat
- `/status` or `/agents`: Displays interactive dashboard of all workspaces.
- `/new <name> [engine]`: Creates a project folder, spawns a Herdr workspace, launches the agent (default: `agy`), and creates a Telegram topic.
- `/read <name>`: Reads the terminal of a specific workspace.
- `/help`: Displays available commands.

---

## Uninstallation

To cleanly stop and remove the service:
```bash
./uninstall.sh
```
This stops and disables the systemd service, removes the unit file, and optionally prompts to remove `~/.config/herdr-telegram`.
