"""Unit tests for JSON Topic Repository."""

import json
import os
import tempfile
import unittest

from bridge.adapters.persistence.json_topic_repository import JsonTopicRepository
from bridge.domain.models import TopicBinding


class TestJsonTopicRepository(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.file_path = os.path.join(self.temp_dir.name, "topics.json")
        self.repo = JsonTopicRepository(self.file_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_save_and_load_topic(self):
        binding = TopicBinding(
            workspace_name="quant-terminal",
            thread_id=42,
            session_id="uuid-1234",
            engine="agy",
            backend="app",
        )
        self.repo.save_topic(binding)

        loaded = self.repo.load_topics()
        self.assertIn("quant-terminal", loaded)
        item = loaded["quant-terminal"]
        self.assertEqual(item.thread_id, 42)
        self.assertEqual(item.session_id, "uuid-1234")
        self.assertEqual(item.backend, "app")

    def test_legacy_format_backward_compatibility(self):
        # Create file with legacy integer format: {"legacy_ws": 105}
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump({"legacy_ws": 105}, f)

        loaded = self.repo.load_topics()
        self.assertIn("legacy_ws", loaded)
        self.assertEqual(loaded["legacy_ws"].thread_id, 105)

    def test_get_workspace_by_thread_id(self):
        binding = TopicBinding(workspace_name="bot-telegram", thread_id=99)
        self.repo.save_topic(binding)
        self.assertEqual(self.repo.get_workspace_by_thread_id(99), "bot-telegram")
        self.assertIsNone(self.repo.get_workspace_by_thread_id(999))

    def test_update_session_id(self):
        binding = TopicBinding(workspace_name="project-x", thread_id=10, session_id="old-uuid")
        self.repo.save_topic(binding)
        self.repo.update_session_id("project-x", "new-uuid")

        loaded = self.repo.get_topic_by_workspace("project-x")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.session_id, "new-uuid")


if __name__ == "__main__":
    unittest.main()
