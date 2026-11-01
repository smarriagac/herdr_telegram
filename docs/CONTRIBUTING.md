# Contributing to Herdr Telegram Bridge

Thank you for your interest in contributing to **Herdr Telegram Bridge**! We welcome community contributions, bug reports, and enhancements.

<p align="right">
  <a href="es/CONTRIBUTING.md">Leer en Español</a>
</p>

---

## Guiding Principles

1. **Zero External Dependencies**: The core daemon and installers must run purely on Python's standard library and OS-native facilities. Do not introduce pip dependencies (`requests`, `python-telegram-bot`, etc.) to the core bridge.
2. **Cross-Platform Parity**: Features should support Linux (`systemd`), macOS (`launchd`), and Windows (`install.ps1` Task Scheduler) cleanly whenever possible.
3. **Robust IPC**: Interactions with Herdr must handle disconnects, missing sockets, and timeouts gracefully.

---

## Local Development Workflow

### 1. Fork & Clone
```bash
git clone https://github.com/your-username/herdr-telegram-bridge.git
cd herdr-telegram-bridge
```

### 2. Manual Execution (Without Service Supervisor)
To debug directly in your terminal:
```bash
python3 bot.py --config config.example.json
```

Or copy your real config:
```bash
cp ~/.config/herdr-telegram/config.json ./config.local.json
python3 bot.py --config ./config.local.json
```

### 3. Syntax & Style Checks
Ensure Python standard library syntax conformance:
```bash
python3 -m py_compile bot.py
```

---

## Commit Guidelines

We enforce the [Conventional Commits](https://www.conventionalcommits.org/) specification for structured changelogs and git history.

### Commit Format
```text
<type>(<optional scope>): <description in imperative mood>

[optional body]

[optional footer(s)]
```

### Types
- `feat`: A new feature or capability.
- `fix`: A bug fix.
- `docs`: Documentation updates or additions.
- `style`: Formatting, missing semicolons, whitespace (no functional change).
- `refactor`: Code restructuring without bug fixes or new features.
- `perf`: Performance optimizations.
- `test`: Adding or updating test cases.
- `chore`: Maintenance tasks, repo scripts, or meta changes.

> [!CAUTION]
> Never add `Co-Authored-By` or AI tool attribution strings to git commits.

---

## Pull Request Checklist

Before submitting a pull request, verify:
- [ ] No new third-party dependencies were added to `requirements.txt` or `bot.py`.
- [ ] Code passes `python3 -m py_compile bot.py`.
- [ ] Tested on at least one target operating system (Linux, macOS, or Windows).
- [ ] Documentation updated in `README.md` or `docs/` if commands or config parameters changed.
- [ ] Commit history follows Conventional Commits.
