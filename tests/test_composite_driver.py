"""Unit tests for Composite Driver routing."""

import unittest
from typing import List, Optional, Tuple

from bridge.adapters.drivers.composite_driver import CompositeHerdrDriver
from bridge.domain.models import AgentInfo
from bridge.domain.ports import HerdrDriverPort


class MockDriver(HerdrDriverPort):
    def __init__(self, name: str, available: bool = True):
        self._name = name
        self._available = available
        self.sent_prompts: List[Tuple[str, str]] = []
        self.sent_keys_log: List[Tuple[str, List[str]]] = []

    @property
    def name(self) -> str:
        return self._name

    def is_available(self) -> bool:
        return self._available

    def list_agents(self) -> Tuple[Optional[List[AgentInfo]], Optional[str]]:
        if self._name == "classic":
            return [
                AgentInfo(id="w1:t1:p1", workspace_label="deportivo", backend="classic"),
            ], None
        else:
            return [
                AgentInfo(id="t1", workspace_label="herdr-desktop", backend="app"),
            ], None

    def create_workspace(self, name: str, engine: str = "agy", folder: Optional[str] = None, session_id: Optional[str] = None):
        return True, f"created on {self._name}", session_id

    def send_prompt(self, target_id: str, prompt_text: str) -> Tuple[bool, str]:
        self.sent_prompts.append((target_id, prompt_text))
        return True, "ok"

    def send_keys(self, target_id: str, keys: List[str]) -> Tuple[bool, str]:
        self.sent_keys_log.append((target_id, keys))
        return True, "ok"

    def read_terminal(self, target_id: str, lines: int = 25) -> Tuple[bool, str]:
        return True, f"output from {self._name}"

    def close_workspace(self, target_id: str) -> Tuple[bool, str]:
        return True, "closed"

    def rename_workspace(self, target_id: str, new_name: str) -> Tuple[bool, str]:
        return True, "renamed"


class TestCompositeDriver(unittest.TestCase):
    def setUp(self):
        self.classic_mock = MockDriver("classic")
        self.app_mock = MockDriver("app")
        self.composite = CompositeHerdrDriver(
            classic_driver=self.classic_mock,
            app_driver=self.app_mock,
            preferred_mode="auto",
        )

    def test_list_agents_merges_both_backends(self):
        agents, err = self.composite.list_agents()
        self.assertIsNone(err)
        self.assertIsNotNone(agents)
        self.assertEqual(len(agents), 2)
        backends = {ag.backend for ag in agents}
        self.assertEqual(backends, {"classic", "app"})

    def test_routes_classic_pane_id_to_classic_driver(self):
        ok, _ = self.composite.send_prompt("w1:t1:p1", "hello classic")
        self.assertTrue(ok)
        self.assertEqual(len(self.classic_mock.sent_prompts), 1)
        self.assertEqual(self.classic_mock.sent_prompts[0], ("w1:t1:p1", "hello classic"))
        self.assertEqual(len(self.app_mock.sent_prompts), 0)

    def test_routes_terminal_id_to_app_driver(self):
        ok, _ = self.composite.send_prompt("t1", "hello desktop")
        self.assertTrue(ok)
        self.assertEqual(len(self.app_mock.sent_prompts), 1)
        self.assertEqual(self.app_mock.sent_prompts[0], ("t1", "hello desktop"))
        self.assertEqual(len(self.classic_mock.sent_prompts), 0)

    def test_routes_by_workspace_name(self):
        # "deportivo" is in classic mock
        self.composite.send_keys("deportivo", ["enter"])
        self.assertEqual(len(self.classic_mock.sent_keys_log), 1)
        self.assertEqual(self.classic_mock.sent_keys_log[0], ("w1:t1:p1", ["enter"]))

        # "herdr-desktop" is in app mock
        self.composite.send_keys("herdr-desktop", ["esc"])
        self.assertEqual(len(self.app_mock.sent_keys_log), 1)
        self.assertEqual(self.app_mock.sent_keys_log[0], ("t1", ["esc"]))


if __name__ == "__main__":
    unittest.main()
