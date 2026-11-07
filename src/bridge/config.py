"""Configuration management for Herdr Telegram Bridge."""

import json
import logging
import os
import sys
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("herdr-bridge.config")


@dataclass
class BridgeConfig:
    bot_token: str
    allowed_chat_id: int
    group_chat_id: Optional[int] = None
    driver: str = "auto"  # 'auto', 'classic', 'app'
    herdr_bin: str = "herdr"
    herdr_app_bin: str = "herdr-app"
    hc_bin: str = "hc"
    projects_dir: str = "~/proyectos"
    topics_file: str = ""
    groq_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None

    def __post_init__(self):
        if not self.topics_file:
            # Default to topics.json in the user's config directory
            if sys.platform == "win32":
                base = os.environ.get("APPDATA", os.path.expanduser("~"))
            else:
                base = os.path.expanduser("~/.config")
            self.topics_file = os.path.join(base, "herdr-telegram", "topics.json")

        self.projects_dir = os.path.expanduser(self.projects_dir)
        self.topics_file = os.path.expanduser(self.topics_file)


def resolve_config_path(cli_override: Optional[str] = None) -> str:
    """Finds configuration file across command-line, env vars, and standard paths."""
    if cli_override:
        return os.path.abspath(os.path.expanduser(cli_override))

    env_path = os.environ.get("HERDR_TELEGRAM_CONFIG")
    if env_path:
        return os.path.abspath(os.path.expanduser(env_path))

    if sys.platform == "win32":
        base_dir = os.environ.get("APPDATA", os.path.expanduser("~"))
        default_dir = os.path.join(base_dir, "herdr-telegram")
    else:
        default_dir = os.path.expanduser("~/.config/herdr-telegram")

    return os.path.join(default_dir, "config.json")


def load_config(config_path: Optional[str] = None) -> BridgeConfig:
    """Loads and validates configuration from JSON file."""
    path = resolve_config_path(config_path)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Configuration file not found at: {path}\n"
            "Create it by copying config.example.json or running install script."
        )

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    bot_token = data.get("bot_token")
    if not bot_token or "BOTFATHER" in bot_token:
        raise ValueError(f"Invalid 'bot_token' in configuration file: {path}")

    allowed_chat_id = data.get("allowed_chat_id")
    if not allowed_chat_id:
        raise ValueError(f"Missing 'allowed_chat_id' in configuration file: {path}")

    topics_dir = os.path.dirname(path)
    topics_default = os.path.join(topics_dir, "topics.json")

    return BridgeConfig(
        bot_token=str(bot_token),
        allowed_chat_id=int(allowed_chat_id),
        group_chat_id=int(data["group_chat_id"]) if data.get("group_chat_id") else None,
        driver=data.get("driver", "auto"),
        herdr_bin=data.get("herdr_bin", "herdr"),
        herdr_app_bin=data.get("herdr_app_bin", "herdr-app"),
        hc_bin=data.get("hc_bin", "hc"),
        projects_dir=data.get("projects_dir", "~/proyectos"),
        topics_file=data.get("topics_file", topics_default),
        groq_api_key=data.get("groq_api_key") or os.environ.get("GROQ_API_KEY"),
        openai_api_key=data.get("openai_api_key") or os.environ.get("OPENAI_API_KEY"),
    )
