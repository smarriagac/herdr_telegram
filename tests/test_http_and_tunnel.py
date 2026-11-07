"""Tests for Mini App HTTP server and Cloudflare tunnel integration."""

import json
import urllib.request
import unittest
from unittest.mock import MagicMock, patch

from bridge.adapters.http.api_server import HttpApiServer
from bridge.adapters.tunnel.cloudflared import CloudflareTunnel
from bridge.application.bot_controller import BotController
from bridge.domain.models import AgentInfo


class FakeDriver:
    def list_agents(self):
        return [
            AgentInfo(
                id="workspace-1",
                name="pet_care",
                status="idle",
                backend="app",
                engine="agy",
                workspace_label="mascotas",
            )
        ], None

    def read_terminal(self, target, lines=40):
        return True, "=== Terminal output for " + target

    def send_keys(self, target, keys):
        return True, "ok"

    def send_prompt(self, target, prompt):
        return True, "prompt sent"


class FakeTopicRepo:
    def load_topics(self):
        return {}

    def get_workspace_by_thread_id(self, thread_id):
        return None


class FakeService:
    def __init__(self):
        self.driver = FakeDriver()

    def read_agent_result(self, target, lines=120):
        return "<b>Resultado</b>", None

    def create_agent(self, name, engine="agy"):
        return "Created", None


class TestHttpServer(unittest.TestCase):
    def setUp(self):
        self.service = FakeService()
        self.topic_repo = FakeTopicRepo()
        # Use random/ephemeral port or 18765
        self.server = HttpApiServer(
            service=self.service,
            topic_repo=self.topic_repo,
            host="127.0.0.1",
            port=18765,
        )
        self.server.start()

    def tearDown(self):
        self.server.stop()

    def test_get_api_agents(self):
        req = urllib.request.urlopen("http://127.0.0.1:18765/api/agents", timeout=3)
        self.assertEqual(req.status, 200)
        data = json.loads(req.read().decode("utf-8"))
        self.assertTrue(data.get("ok"))
        agents = data.get("agents", [])
        self.assertEqual(len(agents), 1)
        self.assertEqual(agents[0]["name"], "pet_care")

    def test_get_api_result(self):
        req = urllib.request.urlopen("http://127.0.0.1:18765/api/agents/workspace-1/result", timeout=3)
        self.assertEqual(req.status, 200)
        data = json.loads(req.read().decode("utf-8"))
        self.assertTrue(data.get("ok"))
        self.assertIn("formatted_html", data)

    def test_get_api_terminal(self):
        req = urllib.request.urlopen("http://127.0.0.1:18765/api/agents/workspace-1/terminal?lines=10", timeout=3)
        self.assertEqual(req.status, 200)
        data = json.loads(req.read().decode("utf-8"))
        self.assertTrue(data.get("ok"))
        self.assertIn("Terminal output", data.get("output", ""))

    def test_static_index_html(self):
        req = urllib.request.urlopen("http://127.0.0.1:18765/", timeout=3)
        self.assertEqual(req.status, 200)
        content = req.read().decode("utf-8")
        self.assertIn("Herdr", content)


class TestCloudflareTunnel(unittest.TestCase):
    def test_tunnel_properties(self):
        tunnel = CloudflareTunnel(local_port=8765, cloudflared_bin="/nonexistent/cloudflared")
        self.assertFalse(tunnel.is_available)
        self.assertIsNone(tunnel.public_url)
        # Starting with non-existent binary returns None gracefully
        self.assertIsNone(tunnel.start(timeout=0.1))

    def test_tunnel_stop(self):
        tunnel = CloudflareTunnel(local_port=8765)
        tunnel.public_url = "https://test.trycloudflare.com"
        tunnel.stop()
        self.assertIsNone(tunnel.public_url)


class TestBotControllerMiniApp(unittest.TestCase):
    def test_app_command_with_tunnel(self):
        mock_telegram = MagicMock()
        mock_service = MagicMock()
        mock_service.build_status_reply.return_value = ("Status text", {"inline_keyboard": []})
        mock_repo = MagicMock()

        tunnel = MagicMock()
        tunnel.public_url = "https://active-test.trycloudflare.com"

        controller = BotController(
            service=mock_service,
            topic_repo=mock_repo,
            telegram=mock_telegram,
            allowed_chat_id=123,
            tunnel=tunnel,
        )

        update = {
            "message": {
                "chat": {"id": 123},
                "from": {"id": 123},
                "text": "/app",
            }
        }
        controller.process_update(update)

        mock_telegram.send_message.assert_called_once()
        args, kwargs = mock_telegram.send_message.call_args
        self.assertEqual(args[0], 123)
        self.assertIn("Mini App", args[1])
        reply_markup = kwargs.get("reply_markup", {})
        inline_kb = reply_markup.get("inline_keyboard", [])
        self.assertEqual(inline_kb[0][0]["web_app"]["url"], "https://active-test.trycloudflare.com")


if __name__ == "__main__":
    unittest.main()
