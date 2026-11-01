"""Unit tests for domain models."""

import unittest
from bridge.domain.models import AgentInfo, TopicBinding, STATUS_CONFIG


class TestDomainModels(unittest.TestCase):
    def test_agent_info_display_name_generation(self):
        ag = AgentInfo(
            id="w1:t1:p1",
            workspace_label="deportivo",
            tab_label="feature",
            name="analyzer",
        )
        self.assertEqual(ag.display_name, "deportivo · feature · <b>analyzer</b>")

    def test_agent_info_defaults(self):
        ag = AgentInfo(id="t1", workspace_label="my-project")
        self.assertEqual(ag.backend, "classic")
        self.assertEqual(ag.status, "unknown")
        self.assertEqual(ag.display_name, "my-project")

    def test_status_config_completeness(self):
        expected_statuses = ["working", "idle", "blocked", "done", "error", "stopped", "unknown"]
        for st in expected_statuses:
            self.assertIn(st, STATUS_CONFIG)
            self.assertIn("icon", STATUS_CONFIG[st])
            self.assertIn("label", STATUS_CONFIG[st])


if __name__ == "__main__":
    unittest.main()
