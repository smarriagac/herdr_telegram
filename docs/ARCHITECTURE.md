# Architecture & Runtime Design

An in-depth guide to how `herdr-telegram-bridge` bridges Telegram Forum Topics, Herdr Unix domain sockets, and autonomous AI coding agents with zero external database dependencies.

<p align="right">
  <a href="es/ARCHITECTURE.md">Leer en Español</a>
</p>

---

## System Overview

```mermaid
sequenceDiagram
    autonumber
    actor Dev as Developer (Mobile Telegram)
    participant TG as Telegram Bot API
    participant Daemon as herdr-telegram-bridge (bot.py)
    participant State as State Watcher Thread
    participant Socket as Herdr Socket (~/.config/herdr/herdr.sock)
    participant Agent as Agent Process (e.g., agy / claude)

    Dev->>TG: Plain message in #📁 deportivo topic
    TG->>Daemon: Long-polling update (message_thread_id)
    Daemon->>Daemon: Map thread_id -> workspace name ("deportivo")
    Daemon->>Socket: IPC Request: submit_prompt(workspace, text)
    Socket->>Agent: Inject stdin / tool call
    
    loop Real-time State Monitoring (1.5s interval)
        State->>Socket: Query process status
        Socket-->>State: Process BLOCKED (waiting confirmation)
        State->>TG: Push alert + Tactile Buttons [Enter] [Yes] [Cancel]
    end

    Dev->>TG: Click [Enter] button
    TG->>Daemon: CallbackQuery (act|enter|pid)
    Daemon->>Socket: IPC Send Input: '\n'
    Socket->>Agent: Terminal Stdin Resumed
```

---

## Detailed System Architecture (Interactive Archify Map)

<p align="center">
  <img src="assets/architecture-detailed.svg" alt="Detailed System Architecture" width="100%">
</p>

> [!TIP]
> Explore the standalone **interactive HTML diagram** featuring dark/light themes, zoom, pan, and animated trace at [architecture-detailed.html](architecture-detailed.html).

---

## Clean Architecture (Hexagonal / Ports & Adapters)

The codebase is organized following **Clean Architecture** principles to separate core domain logic from external frameworks, APIs, and CLI drivers:

```
src/bridge/
├── domain/                  # Enterprise business rules & models (no external deps)
│   ├── models.py            # AgentInfo, TopicBinding, ProcessStatus
│   └── ports.py             # HerdrDriverPort, StateRepositoryPort, TelegramPort
├── adapters/                # Infrastructure implementations of domain ports
│   ├── drivers/             # Backend Execution Adapters
│   │   ├── classic_driver.py   # Herdr Classic (herdr CLI / socket)
│   │   ├── app_driver.py       # Herdr Desktop (herdr-app do / herdr-core hc)
│   │   └── composite_driver.py # Unified dual-driver with automatic backend detection
│   ├── persistence/         # Storage Adapters
│   │   └── json_topic_repository.py  # Atomic topics.json state storage
│   └── telegram/            # Presentation / Transport Adapters
│       └── telegram_client.py        # Python standard library Telegram API client
├── application/             # Application use cases & orchestration
│   ├── agent_service.py     # Agent and workspace lifecycle operations
│   ├── state_watcher.py     # Background daemon thread monitoring agent states
│   └── bot_controller.py    # Telegram update routing and command dispatching
├── config.py                # Configuration loading and validation
└── main.py                  # Composition Root & Dependency Injection
```

### Dual-Driver Architecture: Terminal & Desktop Unification

The bridge supports both Herdr ecosystems seamlessly:
1. **`ClassicHerdrDriver`**: Connects to the traditional `herdr` multiplexer (`herdr server`, `~/.config/herdr/herdr.sock`, `herdr workspace`, `herdr agent`).
2. **`HerdrAppDriver`**: Connects to the modern **Herdr Desktop** app (`herdr-app do space.new`, `herdr-app ls`) and its native execution engine **herdr-core** (`hc send`, `hc read`, `hc wait`, `hc keys`).
3. **`CompositeHerdrDriver` (`"driver": "auto"`)**:
   - Discovers agents running across **both** Terminal workspaces and Desktop spaces concurrently.
   - Smart routing: Inspects target IDs (`w1:t1:p1` vs `t1` / `sp...`) and workspace names to transparently route prompts and keys to the appropriate backend.

---

## Core Components

### 1. Telegram Polling & Whitelist Dispatcher
The main thread continuously polls Telegram's `getUpdates` endpoint using standard library `urllib.request`. 
- **Security Whitelist**: Every update is authenticated against `allowed_chat_id` and `group_chat_id`. Any message from an unauthorized Telegram user ID is discarded immediately.
- **Context Routing**:
  - Messages in `group_chat_id` with a `message_thread_id` are routed to that workspace's dedicated agent.
  - Messages without a thread ID (or in direct private chat) are treated as administrative commands (`/status`, `/new`, `/resume`, `/help`).

### 2. Herdr Socket IPC Layer
Herdr exposes a lightweight Unix domain socket (`~/.config/herdr/herdr.sock`) for low-latency agent orchestration.
- **Protocol**: JSON-RPC over local socket connection.
- **Fallback**: If the socket is unavailable or running on platforms without Unix sockets, commands gracefully degrade to CLI invocation (`herdr workspace ...`, `herdr prompt ...`).

### 3. Topic-to-Workspace State Map (`topics.json`)
Workspace bindings are persisted in a simple atomic JSON file (`~/.config/herdr/topics.json` or platform equivalent):

```json
{
  "deportivo": {
    "thread_id": 4,
    "created_at": "2026-10-31T20:30:00Z",
    "engine": "agy",
    "session_id": "16bb7d4d-18e3-40da-bec0-c5e9cf29caa5"
  }
}
```

This ensures complete state recovery even if the daemon crashes, the host machine reboots, or network connection drops.

### 4. Background State Watcher & Proactive Notifications
A background worker thread (`state_watcher_thread`) periodically queries active processes:
- **Status Change Detection**: Monitors agent transitions (`running`, `idle`, `blocked`, `stopped`).
- **Interactive Prompts**: When an agent requests tool execution confirmation, the bridge sends a tactile inline keyboard (`[Enter]`, `[Yes]`, `[Cancel]`, `[Inspect Terminal]`) directly to the relevant topic.
- **Resilient Callback Parsing**: Button callbacks use a pipe-delimited schema (`act|<action>|<pid>`) ensuring unambiguous routing regardless of process argument whitespace.

---

## Zero-Database Session Persistence

A common architectural question: *Why does the bridge not need SQLite, PostgreSQL, or Redis to store multi-agent conversation history?*

```mermaid
flowchart TD
    subgraph Telegram["Telegram Client"]
        Msg["User Message / Prompt"]
    end

    subgraph Bridge["Telegram Bridge Daemon"]
        Map["topics.json\n(Stores: project -> session_id)"]
    end

    subgraph Runtime["Agent Runtime (Antigravity / Gemini CLI)"]
        Transcript["Local JSONL Storage\n~/.gemini/antigravity-cli/brain/<session_id>/transcript.jsonl"]
        Engine["Agent Execution Engine"]
    end

    Msg --> Bridge
    Bridge --> Map
    Map -.->|"--conversation <session_id>"| Engine
    Engine <--> Transcript
```

### The Persistence Lifecycle
1. **Initial Creation**: When `/new <name>` or `herdr new` launches an agent, the runtime registers a unique UUID for the conversation (`session_id`).
2. **Metadata Sync**: The bridge captures this `session_id` directly from Herdr's process metadata and persists it in `topics.json`.
3. **Local JSONL Storage**: The agent engine natively appends every user prompt, tool call, thinking trace, and model response to its local transcript on disk (`transcript.jsonl`).
4. **Context Recovery (`/resume`)**: When an agent session terminates or machine reboots, executing `/resume <name>` re-invokes:
   ```bash
   herdr workspace run <name> agy --conversation <session_id>
   ```
5. **Seamless Continuation**: The agent engine reloads its historical context directly from the local JSONL file, allowing the user to pick up conversation history without any external database infrastructure.

---

## Reliability & Fault Tolerance

| Scenario | Behavior | Recovery Action |
|---|---|---|
| **Daemon Crash / Killed** | Service supervisor restarts daemon automatically (`systemd` / `launchd` / Task Scheduler). | Daemon re-reads `topics.json` on startup and resumes Telegram polling. |
| **Agent Hangs / Blocks** | State Watcher detects blocked status and pushes inline buttons to topic. | User clicks `[Cancel]` or `[Enter]` on Telegram to unblock the shell. |
| **Network Interruption** | `urllib` requests timeout gracefully with exponential backoff. | Polling resumes automatically once network connectivity is restored. |
| **Host Machine Reboot** | Background daemon starts on boot via user service target. | Workspaces can be resumed on demand via `/resume <name>` or automatically. |

---

## Next Steps

- Review the [Setup Guide](SETUP_TELEGRAM.md) to initialize your bot and supergroup.
- Refer to [Contributing Guidelines](CONTRIBUTING.md) to submit improvements or bug fixes.
