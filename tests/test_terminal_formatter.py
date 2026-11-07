"""Unit tests for terminal output cleaning and Telegram formatting."""

import unittest

from bridge.application.terminal_formatter import (
    clean_terminal_output,
    extract_agent_result,
    format_telegram_markdown,
    safe_truncate_html,
    strip_ansi,
)


class TestTerminalFormatter(unittest.TestCase):
    def test_strip_ansi(self):
        raw = "\x1b[32mSuccess\x1b[0m \x1b[1mBold\x1b[0m"
        self.assertEqual(strip_ansi(raw), "Success Bold")

    def test_clean_terminal_output_removes_tui_chrome(self):
        raw = (
            "Actual output line 1\n"
            "Actual output line 2\n"
            "───────────────────────────────────────────────────────────────────\n"
            ">\n"
            "? for shortcuts                                 Gemini 3.8 Flash · high\n"
        )
        cleaned = clean_terminal_output(raw)
        self.assertEqual(cleaned, "Actual output line 1\nActual output line 2")

    def test_extract_agent_result_finds_assistant_text(self):
        raw = (
            "● Bash(pytest)\n"
            "● Read(~/file.py)\n"
            "▸ Thought for 10s\n"
            "● Edit(~/file.py)\n"
            "\n"
            "  The task is completed successfully.\n"
            "  All tests passed.\n"
            "───────────────────────────────────────────────────────────────────\n"
            ">\n"
            "esc to cancel\n"
        )
        res = extract_agent_result(raw)
        self.assertEqual(res, "The task is completed successfully.\nAll tests passed.")

    def test_extract_agent_result_fallback_when_no_tools(self):
        raw = (
            "Standard terminal output line 1\n"
            "Standard terminal output line 2\n"
            "───────────────────────────────────────────────────────────────────\n"
            ">\n"
        )
        res = extract_agent_result(raw)
        self.assertEqual(
            res, "Standard terminal output line 1\nStandard terminal output line 2"
        )

    def test_format_telegram_markdown(self):
        md = (
            "### Resumen de cambios\n"
            "Se modificó **archivo.py** con `variable = True`.\n"
            "\n"
            "> Nota importante: reiniciar el servicio.\n"
            "\n"
            "```python\n"
            "def foo():\n"
            "    return 42\n"
            "```\n"
            "Ver [PR](https://github.com/org/repo/pull/1)."
        )
        formatted = format_telegram_markdown(md)
        self.assertIn("📌 <b>Resumen de cambios</b>", formatted)
        self.assertIn("<b>archivo.py</b>", formatted)
        self.assertIn("<code>variable = True</code>", formatted)
        self.assertIn("<blockquote>Nota importante: reiniciar el servicio.</blockquote>", formatted)
        self.assertIn('<pre><code class="language-python">def foo():\n    return 42\n</code></pre>', formatted)
        self.assertIn('<a href="https://github.com/org/repo/pull/1">PR</a>', formatted)

    def test_safe_truncate_html(self):
        # Truncate inside <b> and <code>
        long_text = "<b>Texto en negrita <code>" + "palabra " * 500 + "</code></b>"
        truncated = safe_truncate_html(long_text, max_chars=100)
        self.assertTrue(len(truncated) < 300)
        self.assertIn("</code></b>", truncated)
        self.assertIn("<i>[...Mensaje truncado por longitud...]</i>", truncated)


if __name__ == "__main__":
    unittest.main()
