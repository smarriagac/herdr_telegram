# Telegram Bot & Forum Supergroup Setup Guide

Configure your Telegram bot and Forum Supergroup to enable isolated workspace topics, mobile prompt execution, and approval buttons.

---

## Quick Path

1. **Create Bot**: Message [@BotFather](https://t.me/BotFather) on Telegram, run `/newbot`, and save the HTTP API token.
2. **Create Supergroup**: Create a Telegram group, enable **Topics** in Group Settings, and add your bot.
3. **Grant Admin Permissions**: Promote the bot to Administrator with **Manage Topics** and **Send Messages**.
4. **Discover IDs & Configure**: Retrieve your personal user ID and group ID, then paste them into `config.json`.

---

## Detailed Step-by-Step

### 1. Create Bot with @BotFather

1. Open Telegram and search for [@BotFather](https://t.me/BotFather) (verified account with blue checkmark).
2. Send `/newbot`.
3. Choose a friendly name (e.g., `My Coding Fleet`).
4. Choose a username ending in `bot` (e.g., `my_fleet_herdr_bot`).
5. Copy the generated HTTP API token (format: `123456789:ABCdefGHIjklMNOpqrSTUvwxYZ`).
6. *(Optional)* Disable group privacy if you want the bot to see all messages:
   - Send `/setprivacy` to `@BotFather`.
   - Select your bot.
   - Choose **Disable** (this allows the bot to receive prompts without typing `/prompt`).

---

### 2. Create the Forum Supergroup

The bridge uses Telegram Forum Topics to create one dedicated thread per Herdr workspace.

1. In Telegram, create a **New Group** (e.g., `AI Agent Operations`).
2. Add your newly created bot to the group.
3. Open **Group Info** > **Edit** (pencil icon).
4. Select **Topics** (or **Forum**) and toggle it **ON**.
   > [!NOTE]
   > Enabling Topics converts the standard Telegram group into a Supergroup with forum threads.
5. Save changes.

---

### 3. Promote Bot to Administrator

1. In **Group Info**, navigate to **Administrators** > **Add Admin**.
2. Select your bot.
3. Ensure the following permissions are enabled:
   - [x] **Manage Topics** *(Required to create and close workspace threads)*
   - [x] **Send Messages**
   - [x] **Delete Messages** *(Optional, for cleanup)*
   - [x] **Pin Messages** *(Recommended for status pinning)*
4. Save admin settings.

---

### 4. Discover Your IDs

The bridge uses strict whitelist security to prevent unauthorized users from interacting with your shell.

#### Option A: Personal User ID (`allowed_chat_id`)
- Message [@userinfobot](https://t.me/userinfobot) or [@raw_data_bot](https://t.me/raw_data_bot).
- Copy the integer `Id` (e.g., `809438653`).

#### Option B: Supergroup Chat ID (`group_chat_id`)
- Send a message like `/status` in the General topic of your supergroup.
- Inspect the daemon log:
  ```bash
  # Linux systemd
  journalctl --user -u herdr-telegram.service -n 20 --no-pager
  
  # macOS / Windows
  # Look for incoming update with chat.id starting with -100...
  ```
- Supergroup IDs always start with `-100` (e.g., `-1004353505956`).

---

### 5. Final Configuration

Update your `config.json`:

```json
{
  "bot_token": "YOUR_BOTFATHER_TOKEN_HERE",
  "allowed_chat_id": 809438653,
  "group_chat_id": -1004353505956,
  "herdr_bin": "herdr",
  "projects_dir": "~/proyectos"
}
```

Restart the service:
```bash
# Linux
systemctl --user restart herdr-telegram.service

# macOS
launchctl unload ~/Library/LaunchAgents/com.herdr.telegram.plist
launchctl load -w ~/Library/LaunchAgents/com.herdr.telegram.plist

# Windows PowerShell
Restart-ScheduledTask -TaskName "HerdrTelegramBridge"
```

---

## Verification Checklist

- [ ] Bot responds to `/status` when sent in a private message.
- [ ] Running `/new demo` creates a new forum topic `#📁 demo` in your Supergroup.
- [ ] Messages sent inside `#📁 demo` trigger prompts in the corresponding Herdr agent.
- [ ] Inline approval buttons (`Enter`, `Yes`, `Cancel`) respond promptly when clicked.

---

## Next Steps

- Explore [Architecture & Session Persistence](ARCHITECTURE.md) to understand state synchronization and agent transcript recovery.
- Consult the main [README](../README.md#commands--controls) for the complete command reference.
