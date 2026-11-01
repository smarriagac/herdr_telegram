"""Domain models for Herdr Telegram Bridge."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class AgentInfo:
    """Represents an active or observed AI agent process across Herdr backends."""

    id: str  # e.g., 'w1:t1:p1' for Classic or 't1' for Herdr-App/Core
    workspace_label: str
    status: str = "unknown"  # 'working', 'idle', 'blocked', 'done', 'error', 'stopped'
    name: Optional[str] = None
    workspace_id: Optional[str] = None
    tab_id: Optional[str] = None
    tab_label: str = ""
    session_id: Optional[str] = None
    engine: str = "agy"
    backend: str = "classic"  # 'classic' | 'app'
    display_name: str = ""
    raw_metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.display_name:
            parts = []
            if self.workspace_label:
                parts.append(self.workspace_label)
            if self.tab_label and self.tab_label != "1":
                parts.append(self.tab_label)
            if self.name:
                parts.append(f"<b>{self.name}</b>")
            self.display_name = " · ".join(parts) if parts else self.id


@dataclass
class TopicBinding:
    """Represents the mapping between a workspace/space and a Telegram topic."""

    workspace_name: str
    thread_id: int
    session_id: Optional[str] = None
    engine: str = "agy"
    backend: str = "auto"
    created_at: Optional[str] = None


STATUS_CONFIG = {
    "working": {"icon": "⚡", "label": "Trabajando", "color": "blue"},
    "idle": {"icon": "💤", "label": "En espera", "color": "gray"},
    "blocked": {
        "icon": "⏳",
        "label": "Esperando confirmación",
        "color": "yellow",
    },
    "done": {"icon": "✅", "label": "Completado", "color": "green"},
    "error": {"icon": "❌", "label": "Error", "color": "red"},
    "stopped": {"icon": "⏹️", "label": "Detenido", "color": "gray"},
    "unknown": {"icon": "❓", "label": "Desconocido", "color": "gray"},
}
