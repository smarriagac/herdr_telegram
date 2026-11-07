"""Utilities for cleaning and formatting AI agent terminal output for Telegram."""

import html
import re
import textwrap
from typing import List, Optional

ANSI_REGEX = re.compile(
    r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])|"
    r"\x1B\][^\x07\x1B]*(?:\x07|\x1B\\)"
)

TUI_BOTTOM_PATTERNS = [
    re.compile(r"^[─═\-_]{3,}$"),
    re.compile(r"^\s*>\s*$"),
    re.compile(
        r".*(\? for shortcuts|esc to (?:cancel|interrupt|dismiss)|ctrl\+o to expand|enter to select).*",
        re.I,
    ),
    re.compile(
        r".*(?:Gemini|Claude|GPT|DeepSeek|Llama|Qwen|Opus|Sonnet)\s+[0-9\.]+",
        re.I,
    ),
    re.compile(r"^\s*└?\s*Tip:.*", re.I),
    re.compile(
        r"^\s*[⣾⣽⣻⢿⡿⣟⣯⣷⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏]\s+(?:Running|Thinking|Waiting|Executing).*",
        re.I,
    ),
    re.compile(r"^\s*┃.*"),
    re.compile(r"^\s*⎿\s*.*"),
    re.compile(r"^\s*>\s*/\w+.*"),
    re.compile(r"^\s*⚠\s*Conversation already open.*", re.I),
    re.compile(r"^\s*●\s+.*", re.I),
]

TOOL_LINE_PATTERN = re.compile(
    r"^\s*(?:●\s*(?:\[\d{2}:\d{2}:\d{2}\]|\(?[a-zA-Z0-9_\-]+\)?|cd\s+|[a-zA-Z0-9_\-\./]+)?|"
    r"[✔✖▶]\s*(?:Bash|Read|Edit|Write|Glob|Grep|Task|Search|Run|Command|Todo|AskUser)|"
    r"▸\s*Thought|⎿\s*(?:Exited|Ran|Running))",
    re.I,
)


def strip_ansi(raw: str) -> str:
    """Removes ANSI escape codes and terminal control sequences."""
    return ANSI_REGEX.sub("", raw)


def clean_terminal_output(raw: str) -> str:
    """Strips ANSI sequences and trailing TUI status/prompt chrome."""
    clean = strip_ansi(raw)
    lines = clean.splitlines()

    # Trim trailing lines matching TUI bottom patterns or empty lines
    while lines:
        last = lines[-1].strip()
        if not last:
            lines.pop()
            continue
        if any(p.match(last) for p in TUI_BOTTOM_PATTERNS):
            lines.pop()
            continue
        break

    return "\n".join(lines)


def extract_agent_result(raw: str) -> str:
    """Extracts the final assistant response after tool calls, or cleaned output."""
    cleaned = clean_terminal_output(raw)
    lines = cleaned.splitlines()

    last_tool_idx = -1
    for i, line in enumerate(lines):
        if TOOL_LINE_PATTERN.match(line):
            last_tool_idx = i

    if last_tool_idx != -1 and last_tool_idx < len(lines) - 1:
        extracted = lines[last_tool_idx + 1 :]
        while extracted and not extracted[0].strip():
            extracted.pop(0)
        # If what followed the last tool call is substantive text, use it
        substantive = textwrap.dedent("\n".join(extracted)).strip()
        if substantive:
            return substantive

    return textwrap.dedent(cleaned).strip()


def format_telegram_markdown(text: str) -> str:
    """Converts common Markdown constructs safely into Telegram HTML."""
    text = textwrap.dedent(text).strip()
    placeholders: List[str] = []

    def stash(content: str) -> str:
        idx = len(placeholders)
        placeholders.append(content)
        return f"___STASH_{idx}___"

    # 1. Stash fenced code blocks (auto-collapse long blocks/diffs with expandable blockquotes)
    def replace_code_block(m):
        lang = m.group(1) or ""
        code = m.group(2)
        clean_code = html.escape(code, quote=False)
        if lang:
            inner = f'<pre><code class="language-{lang}">{clean_code}</code></pre>'
        else:
            inner = f"<pre>{clean_code}</pre>"
        if clean_code.count("\n") >= 6 or lang in ("diff", "patch"):
            return stash(f"<blockquote expandable>{inner}</blockquote>")
        return stash(inner)

    text = re.sub(
        r"```([a-zA-Z0-9_\-]+)?\n?([\s\S]*?)```", replace_code_block, text
    )

    # 2. Stash inline code
    def replace_inline_code(m):
        code = m.group(1)
        clean_code = html.escape(code, quote=False)
        return stash(f"<code>{clean_code}</code>")

    text = re.sub(r"`([^`\n]+)`", replace_inline_code, text)

    # 3. Stash blockquotes (expandable if >= 3 lines)
    def replace_blockquote(m):
        content = m.group(0)
        lines = [re.sub(r"^>\s?", "", line) for line in content.splitlines()]
        escaped_lines = [html.escape(line, quote=False) for line in lines]
        tag = "blockquote expandable" if len(lines) >= 3 else "blockquote"
        return stash(f"<{tag}>{chr(10).join(escaped_lines)}</blockquote>")

    text = re.sub(r"(?m)(?:^>[^\n]*(?:\n|$))+", replace_blockquote, text)

    # 4. Escape remaining raw text (keep quotes as is for natural reading)
    text = html.escape(text, quote=False)

    # 5. Headers: # Header -> 📌 <b>Header</b> (supports leading whitespace and #{1,6})
    text = re.sub(r"(?m)^[ \t]*#{1,6}[ \t]+([^\n]+)$", r"📌 <b>\1</b>", text)

    # 6. Numbered section titles ending with colon (e.g. "1. Section description:")
    text = re.sub(
        r"(?m)^([ \t]*)(\d+\.[ \t]+[^:\n]{3,80}:)", r"\1<b>\2</b>", text
    )

    # 7. Bold: **text**
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)

    # 8. Markdown links: [text](http...)
    text = re.sub(
        r"\[([^\]]+)\]\((https?://[^\s\)]+)\)", r'<a href="\2">\1</a>', text
    )

    # 9. Divider lines (long rules -> clean mobile divider)
    text = re.sub(r"(?m)^[─═\-_]{3,}$", "──────────────────────────", text)

    # 10. Restore stashed blocks
    for idx, content in enumerate(placeholders):
        text = text.replace(f"___STASH_{idx}___", content)

    return text


def extract_live_activity(raw: str) -> str:
    """Extracts a concise one-line summary of what the agent is currently doing."""
    clean = strip_ansi(raw)
    lines = [l.strip() for l in clean.splitlines() if l.strip()]
    for line in reversed(lines[-6:]):
        # Spinner/activity indicator
        m_spin = re.match(
            r"^[⣾⣽⣻⢿⡿⣟⣯⣷⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏]\s+(.*)", line
        )
        if m_spin:
            return m_spin.group(1)[:50]

        # Thinking block
        m_thought = re.match(
            r"^▸\s*Thought(?:\s+for\s+([0-9a-zA-Z\s]+))?", line, re.I
        )
        if m_thought:
            dur = m_thought.group(1) or ""
            return f"Pensando... ({dur.strip()})" if dur else "Pensando..."

        # Tool call like ● Bash(pytest) or ● Read(path)
        m_tool = re.match(
            r"^[●✔▶]\s*(?:\[\d{2}:\d{2}:\d{2}\]\s*)?([a-zA-Z0-9_\-]+)\((.*?)\)",
            line,
        )
        if m_tool:
            tool_name = m_tool.group(1)
            arg = m_tool.group(2)
            arg_short = arg.split("/")[-1] if "/" in arg else arg
            return f"{tool_name}({arg_short})"[:50]

        # General command line
        m_cmd = re.match(
            r"^[●✔▶]\s*(?:\[\d{2}:\d{2}:\d{2}\]\s*)?(.*)", line
        )
        if m_cmd and not m_cmd.group(1).startswith("Conversation"):
            return m_cmd.group(1)[:50]

    return "Procesando..."


def safe_truncate_html(text: str, max_chars: int = 3900) -> str:
    """Truncates text safely at word/line boundaries, balancing unclosed HTML tags."""
    if len(text) <= max_chars:
        return text

    truncated = text[:max_chars]
    last_break = max(truncated.rfind("\n"), truncated.rfind(" "))
    if last_break > int(max_chars * 0.7):
        truncated = truncated[:last_break]

    tag_regex = re.compile(r"<(/?)([a-zA-Z0-9]+)(?:\s+[^>]*)?>")
    open_tags: List[str] = []
    for match in tag_regex.finditer(truncated):
        is_closing = bool(match.group(1))
        tag_name = match.group(2).lower()
        if is_closing:
            if open_tags and open_tags[-1] == tag_name:
                open_tags.pop()
        else:
            open_tags.append(tag_name)

    closing_suffix = "".join(f"</{tag}>" for tag in reversed(open_tags))
    return truncated + closing_suffix + "\n\n<i>[...Mensaje truncado por longitud...]</i>"
