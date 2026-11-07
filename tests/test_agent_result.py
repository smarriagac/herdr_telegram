"""Unit tests for agent result extraction and Telegram presentation."""

import unittest
from typing import Any, Dict, List, Optional, Tuple

from bridge.application.agent_service import AgentBridgeService
from bridge.application.bot_controller import BotController
from bridge.application.state_watcher import StateWatcher
from bridge.domain.models import AgentInfo, TopicBinding
from bridge.domain.ports import HerdrDriverPort, StateRepositoryPort, TelegramPort


class FakeDriver(HerdrDriverPort):
    def __init__(self, output: str = "", available: bool = True):
        self._output = output
        self._available = available
        self.read_calls: List[Tuple[str, int]] = []
        self.sent_prompts: List[Tuple[str, str]] = []

    @property
    def name(self) -> str:
        return "fake"

    def is_available(self) -> bool:
        return self._available

    def list_agents(self) -> Tuple[Optional[List[AgentInfo]], Optional[str]]:
        return [
            AgentInfo(
                id="w1:p1",
                workspace_label="mi-proyecto",
                status="idle",
                name="worker",
                engine="agy",
                backend="classic",
            )
        ], None

    def create_workspace(
        self,
        name: str,
        engine: str = "agy",
        folder: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Tuple[bool, str, Optional[str]]:
        return True, "created", None

    def send_prompt(self, target_id: str, prompt_text: str) -> Tuple[bool, str]:
        self.sent_prompts.append((target_id, prompt_text))
        return True, "ok"

    def send_keys(self, target_id: str, keys: List[str]) -> Tuple[bool, str]:
        return True, "ok"

    def read_terminal(self, target_id: str, lines: int = 25) -> Tuple[bool, str]:
        self.read_calls.append((target_id, lines))
        return True, self._output

    def close_workspace(self, target_id: str) -> Tuple[bool, str]:
        return True, "closed"

    def rename_workspace(self, target_id: str, new_name: str) -> Tuple[bool, str]:
        return True, "renamed"


class FakeTopicRepo(StateRepositoryPort):
    def __init__(self):
        self.topics: Dict[str, TopicBinding] = {}

    def load_topics(self) -> Dict[str, TopicBinding]:
        return self.topics

    def save_topic(self, binding: TopicBinding) -> bool:
        self.topics[binding.workspace_name] = binding
        return True

    def delete_topic(self, workspace_name: str) -> bool:
        if workspace_name in self.topics:
            del self.topics[workspace_name]
            return True
        return False

    def get_topic_by_workspace(self, workspace_name: str) -> Optional[TopicBinding]:
        return self.topics.get(workspace_name)

    def get_workspace_by_thread_id(self, thread_id: int) -> Optional[str]:
        for k, v in self.topics.items():
            if v.thread_id == thread_id:
                return k
        return None

    def update_session_id(self, workspace_name: str, session_id: str) -> bool:
        if workspace_name in self.topics:
            self.topics[workspace_name].session_id = session_id
            return True
        return False


class FakeTelegram(TelegramPort):
    def __init__(self):
        self.sent_messages: List[Dict[str, Any]] = []
        self.edited_messages: List[Dict[str, Any]] = []
        self.answered_callbacks: List[Dict[str, Any]] = []

    def send_message(
        self,
        chat_id: int,
        text: str,
        reply_markup: Optional[Dict[str, Any]] = None,
        message_thread_id: Optional[int] = None,
        parse_mode: str = "HTML",
    ) -> Optional[Dict[str, Any]]:
        self.sent_messages.append({
            "chat_id": chat_id,
            "text": text,
            "reply_markup": reply_markup,
            "message_thread_id": message_thread_id,
        })
        return {"ok": True, "result": {"message_id": len(self.sent_messages)}}

    def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: Optional[Dict[str, Any]] = None,
        parse_mode: str = "HTML",
    ) -> Optional[Dict[str, Any]]:
        self.edited_messages.append({
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "reply_markup": reply_markup,
        })
        return {"ok": True}

    def answer_callback_query(
        self, callback_query_id: str, text: Optional[str] = None, show_alert: bool = False
    ) -> bool:
        self.answered_callbacks.append({
            "id": callback_query_id,
            "text": text,
            "show_alert": show_alert,
        })
        return True

    def create_forum_topic(
        self, chat_id: int, name: str, icon_custom_emoji_id: Optional[str] = None
    ) -> Optional[int]:
        return 123

    def close_forum_topic(self, chat_id: int, message_thread_id: int) -> bool:
        return True

    def get_file(self, file_id: str) -> Optional[Dict[str, Any]]:
        return {"file_id": file_id, "file_path": "voice/test.oga"}

    def download_file(self, file_path: str) -> Optional[bytes]:
        return b"fake-audio-bytes"

    def set_my_commands(self, commands: List[Dict[str, str]]) -> bool:
        return True

    def get_updates(
        self, offset: Optional[int] = None, timeout: int = 25
    ) -> Optional[List[Dict[str, Any]]]:
        return []


class TestAgentResult(unittest.TestCase):
    def setUp(self):
        self.sample_output = (
            "● Bash(pytest)\n"
            "● Read(src/app.py)\n"
            "▸ Thought for 5s\n"
            "● Edit(src/app.py)\n"
            "\n"
            "  ### Resumen del Trabajo\n"
            "  Se corrigió el error en `app.py`.\n"
            "  **Resultado**: 100% de tests pasando.\n"
            "───────────────────────────────────────────────────────────────────\n"
            ">\n"
            "? for shortcuts                                 Gemini 3.8 Flash · high\n"
        )
        self.driver = FakeDriver(output=self.sample_output)
        self.topic_repo = FakeTopicRepo()
        self.telegram = FakeTelegram()
        self.service = AgentBridgeService(
            driver=self.driver,
            topic_repo=self.topic_repo,
            telegram=self.telegram,
            allowed_chat_id=12345,
        )
        self.controller = BotController(
            service=self.service,
            topic_repo=self.topic_repo,
            telegram=self.telegram,
            allowed_chat_id=12345,
        )

    def test_read_agent_result_formats_header_and_body(self):
        msg, markup = self.service.read_agent_result("w1:p1")
        self.assertIn("🎯 <b>Resultado:", msg)
        self.assertIn("mi-proyecto", msg)
        self.assertIn("📌 <b>Resumen del Trabajo</b>", msg)
        self.assertIn("<code>app.py</code>", msg)
        self.assertIn("<b>Resultado</b>:", msg)
        self.assertNotIn("? for shortcuts", msg)
        self.assertNotIn("● Bash", msg)

        # Check inline keyboard
        buttons = markup["inline_keyboard"]
        button_texts = [b["text"] for row in buttons for b in row]
        self.assertIn("🔄 Recargar", button_texts)
        self.assertIn("💬 Nueva Orden", button_texts)
        self.assertIn("🖥️ Terminal Cruda", button_texts)
        self.assertIn("📋 Panel Principal", button_texts)

    def test_callback_query_result_action(self):
        cb_query = {
            "id": "cq_100",
            "data": "act|result|w1:p1",
            "from": {"id": 12345},
            "message": {
                "message_id": 999,
                "chat": {"id": 12345},
            },
        }
        self.controller.process_update({"callback_query": cb_query})
        self.assertEqual(len(self.telegram.sent_messages), 1)
        sent = self.telegram.sent_messages[0]
        self.assertIn("🎯 <b>Resultado:", sent["text"])
        self.assertIn("📌 <b>Resumen del Trabajo</b>", sent["text"])

    def test_callback_query_result_reload_edits_message(self):
        cb_query = {
            "id": "cq_101",
            "data": "act|result_reload|w1:p1",
            "from": {"id": 12345},
            "message": {
                "message_id": 999,
                "chat": {"id": 12345},
            },
        }
        self.controller.process_update({"callback_query": cb_query})
        self.assertEqual(len(self.telegram.edited_messages), 1)
        edited = self.telegram.edited_messages[0]
        self.assertEqual(edited["message_id"], 999)
        self.assertIn("🎯 <b>Resultado:", edited["text"])

    def test_slash_command_result(self):
        msg = {
            "text": "/result w1:p1",
            "from": {"id": 12345},
            "chat": {"id": 12345},
        }
        self.controller.process_update({"message": msg})
        self.assertEqual(len(self.telegram.sent_messages), 1)
        sent = self.telegram.sent_messages[0]
        self.assertIn("🎯 <b>Resultado:", sent["text"])

    def test_text_command_ver_resultado(self):
        msg = {
            "text": "Ver resultado",
            "from": {"id": 12345},
            "chat": {"id": 12345},
        }
        self.controller.process_update({"message": msg})
        self.assertEqual(len(self.telegram.sent_messages), 1)
        sent = self.telegram.sent_messages[0]
        self.assertIn("🎯 <b>Resultado:", sent["text"])

    def test_state_watcher_creates_result_callback(self):
        watcher = StateWatcher(
            service=self.service,
            driver=self.driver,
            topic_repo=self.topic_repo,
            telegram=self.telegram,
        )
        agent = AgentInfo(id="w1:p1", workspace_label="demo", status="idle")
        watcher._handle_state_transition(
            agent=agent,
            old_status="working",
            new_status="idle",
            chat_id=12345,
            thread_id=None,
        )
        self.assertEqual(len(self.telegram.sent_messages), 1)
        msg = self.telegram.sent_messages[0]
        markup = msg["reply_markup"]
        btn = markup["inline_keyboard"][0][0]
        self.assertEqual(btn["callback_data"], "act|result|w1:p1")
        self.assertIn("Ver resultado", btn["text"])

    def test_callback_query_quick_action_dispatches_prompt(self):
        cb_query = {
            "id": "cq_quick_1",
            "data": "act|quick|test|w1:p1",
            "from": {"id": 12345},
            "message": {
                "message_id": 999,
                "chat": {"id": 12345},
            },
        }
        self.controller.process_update({"callback_query": cb_query})
        self.assertEqual(len(self.driver.sent_prompts), 1)
        target, prompt = self.driver.sent_prompts[0]
        self.assertEqual(target, "w1:p1")
        self.assertIn("tests", prompt.lower())

    def test_state_watcher_live_banner_lifecycle(self):
        watcher = StateWatcher(
            service=self.service,
            driver=self.driver,
            topic_repo=self.topic_repo,
            telegram=self.telegram,
        )
        agent = AgentInfo(id="w1:p1", workspace_label="demo", status="working")
        
        # 1. Transition to working -> creates live banner
        watcher._handle_state_transition(
            agent=agent,
            old_status="idle",
            new_status="working",
            chat_id=12345,
            thread_id=10,
        )
        self.assertEqual(len(self.telegram.sent_messages), 1)
        banner_msg = self.telegram.sent_messages[0]
        self.assertIn("Iniciando tarea", banner_msg["text"])
        self.assertIn("w1:p1", watcher._active_banners)

        # 2. Transition from working to idle -> edits banner into completion card
        agent.status = "idle"
        watcher._handle_state_transition(
            agent=agent,
            old_status="working",
            new_status="idle",
            chat_id=12345,
            thread_id=10,
        )
        self.assertEqual(len(self.telegram.edited_messages), 1)
        completed_card = self.telegram.edited_messages[0]
        self.assertIn("¡Tarea Completada!", completed_card["text"])
        self.assertNotIn("w1:p1", watcher._active_banners)

    def test_voice_prompt_with_mock_transcriber(self):
        class MockTranscriber:
            is_configured = True
            def transcribe(self, audio_bytes, filename):
                return True, "corregir el bug de autenticación"

        self.controller.transcriber = MockTranscriber()
        self.topic_repo.save_topic(TopicBinding(workspace_name="demo-ws", thread_id=50))
        self.controller.group_chat_id = 99999

        voice_msg = {
            "chat": {"id": 99999},
            "from": {"id": 12345},
            "message_thread_id": 50,
            "voice": {"file_id": "voice_123"},
        }
        self.controller.process_update({"message": voice_msg})
        self.assertEqual(len(self.driver.sent_prompts), 1)
        target, prompt = self.driver.sent_prompts[0]
        self.assertEqual(target, "demo-ws")
        self.assertEqual(prompt, "corregir el bug de autenticación")


if __name__ == "__main__":
    unittest.main()
