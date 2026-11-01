"""JSON File Persistence Adapter for Topics and Sessions."""

import json
import logging
import os
import tempfile
from typing import Dict, Optional

from bridge.domain.models import TopicBinding
from bridge.domain.ports import StateRepositoryPort

logger = logging.getLogger("herdr-bridge.persistence")


class JsonTopicRepository(StateRepositoryPort):
    """Persists topic bindings and session UUIDs in topics.json atomically."""

    def __init__(self, file_path: str):
        self.file_path = os.path.abspath(os.path.expanduser(file_path))

    def _ensure_dir(self):
        parent = os.path.dirname(self.file_path)
        if parent and not os.path.exists(parent):
            os.makedirs(parent, exist_ok=True)

    def load_topics(self) -> Dict[str, TopicBinding]:
        if not os.path.exists(self.file_path):
            return {}

        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.error("Failed to load topics file %s: %s", self.file_path, e)
            return {}

        result: Dict[str, TopicBinding] = {}
        for ws, val in data.items():
            if isinstance(val, int):
                # Legacy simple integer format
                result[ws] = TopicBinding(
                    workspace_name=ws, thread_id=val, backend="auto"
                )
            elif isinstance(val, dict):
                result[ws] = TopicBinding(
                    workspace_name=ws,
                    thread_id=val.get("thread_id", 0),
                    session_id=val.get("session_id"),
                    engine=val.get("engine", "agy"),
                    backend=val.get("backend", "auto"),
                    created_at=val.get("created_at"),
                )
        return result

    def _save_raw(self, raw_data: Dict[str, dict]):
        self._ensure_dir()
        dir_name = os.path.dirname(self.file_path)
        try:
            fd, tmp_path = tempfile.mkstemp(dir=dir_name, prefix="topics_", suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(raw_data, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, self.file_path)
        except Exception as e:
            logger.error("Failed to save topics file %s: %s", self.file_path, e)

    def save_topic(self, binding: TopicBinding) -> None:
        topics = self.load_topics()
        topics[binding.workspace_name] = binding

        raw = {}
        for ws, b in topics.items():
            raw[ws] = {
                "thread_id": b.thread_id,
                "session_id": b.session_id,
                "engine": b.engine,
                "backend": b.backend,
                "created_at": b.created_at,
            }
        self._save_raw(raw)

    def get_topic_by_workspace(self, workspace_name: str) -> Optional[TopicBinding]:
        topics = self.load_topics()
        return topics.get(workspace_name)

    def get_workspace_by_thread_id(self, thread_id: int) -> Optional[str]:
        topics = self.load_topics()
        for ws, b in topics.items():
            if b.thread_id == thread_id:
                return ws
        return None

    def update_session_id(self, workspace_name: str, session_id: str) -> None:
        topics = self.load_topics()
        if workspace_name in topics:
            topics[workspace_name].session_id = session_id
            self.save_topic(topics[workspace_name])

    def delete_topic(self, workspace_name: str) -> None:
        topics = self.load_topics()
        if workspace_name in topics:
            del topics[workspace_name]
            raw = {
                ws: {
                    "thread_id": b.thread_id,
                    "session_id": b.session_id,
                    "engine": b.engine,
                    "backend": b.backend,
                    "created_at": b.created_at,
                }
                for ws, b in topics.items()
            }
            self._save_raw(raw)
