"""Domain ports (interfaces) for Herdr Telegram Bridge."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

from bridge.domain.models import AgentInfo, TopicBinding


class HerdrDriverPort(ABC):
    """Port for communicating with Herdr backends (Classic CLI or Herdr-App/Core)."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Returns the name identifier of this driver."""
        raise NotImplementedError

    @abstractmethod
    def is_available(self) -> bool:
        """Checks if the underlying service/executable is available and running."""
        raise NotImplementedError

    @abstractmethod
    def list_agents(self) -> Tuple[Optional[List[AgentInfo]], Optional[str]]:
        """Lists active agents with parsed metadata. Returns (agents, error)."""
        raise NotImplementedError

    @abstractmethod
    def create_workspace(
        self,
        name: str,
        engine: str = "agy",
        folder: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Tuple[bool, str, Optional[str]]:
        """Creates a new workspace/space and starts an agent.

        Returns (success, message, session_id).
        """
        raise NotImplementedError

    @abstractmethod
    def send_prompt(self, target_id: str, prompt_text: str) -> Tuple[bool, str]:
        """Submits an instruction or prompt to the target agent. Returns (success, message)."""
        raise NotImplementedError

    @abstractmethod
    def send_keys(self, target_id: str, keys: List[str]) -> Tuple[bool, str]:
        """Sends key sequences (e.g. ['enter'], ['esc'], ['y', 'enter']) to the target."""
        raise NotImplementedError

    @abstractmethod
    def read_terminal(self, target_id: str, lines: int = 25) -> Tuple[bool, str]:
        """Reads recent terminal output from the agent process. Returns (success, text)."""
        raise NotImplementedError

    @abstractmethod
    def close_workspace(self, target_id: str) -> Tuple[bool, str]:
        """Closes the workspace or terminates the terminal/space. Returns (success, message)."""
        raise NotImplementedError

    @abstractmethod
    def rename_workspace(self, target_id: str, new_name: str) -> Tuple[bool, str]:
        """Renames a workspace or agent. Returns (success, message)."""
        raise NotImplementedError


class StateRepositoryPort(ABC):
    """Port for persisting workspace topic bindings and agent session IDs."""

    @abstractmethod
    def load_topics(self) -> Dict[str, TopicBinding]:
        """Loads all topic bindings."""
        raise NotImplementedError

    @abstractmethod
    def save_topic(self, binding: TopicBinding) -> None:
        """Saves or updates a topic binding."""
        raise NotImplementedError

    @abstractmethod
    def get_topic_by_workspace(self, workspace_name: str) -> Optional[TopicBinding]:
        """Finds binding by workspace name."""
        raise NotImplementedError

    @abstractmethod
    def get_workspace_by_thread_id(self, thread_id: int) -> Optional[str]:
        """Finds workspace name by Telegram thread ID."""
        raise NotImplementedError

    @abstractmethod
    def update_session_id(self, workspace_name: str, session_id: str) -> None:
        """Updates the session ID for a workspace."""
        raise NotImplementedError

    @abstractmethod
    def delete_topic(self, workspace_name: str) -> None:
        """Removes a topic binding."""
        raise NotImplementedError


class TelegramPort(ABC):
    """Port for interacting with the Telegram Bot API."""

    @abstractmethod
    def send_message(
        self,
        chat_id: int,
        text: str,
        reply_markup: Optional[Dict[str, Any]] = None,
        message_thread_id: Optional[int] = None,
        parse_mode: str = "HTML",
    ) -> Optional[Dict[str, Any]]:
        """Sends a message to Telegram."""
        raise NotImplementedError

    @abstractmethod
    def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: Optional[Dict[str, Any]] = None,
        parse_mode: str = "HTML",
    ) -> Optional[Dict[str, Any]]:
        """Edits an existing Telegram message."""
        raise NotImplementedError

    @abstractmethod
    def answer_callback_query(
        self,
        callback_query_id: str,
        text: Optional[str] = None,
        show_alert: bool = False,
    ) -> bool:
        """Acknowledges a button callback query."""
        raise NotImplementedError

    @abstractmethod
    def create_forum_topic(
        self, chat_id: int, name: str, icon_custom_emoji_id: Optional[str] = None
    ) -> Optional[int]:
        """Creates a forum topic in a supergroup and returns its message_thread_id."""
        raise NotImplementedError

    @abstractmethod
    def close_forum_topic(self, chat_id: int, message_thread_id: int) -> bool:
        """Closes a forum topic in a supergroup."""
        raise NotImplementedError

    @abstractmethod
    def get_file(self, file_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves file info from Telegram API."""
        raise NotImplementedError

    @abstractmethod
    def download_file(self, file_path: str) -> Optional[bytes]:
        """Downloads raw bytes of a file from Telegram API."""
        raise NotImplementedError

    def set_chat_menu_button(
        self, chat_id: Optional[int] = None, menu_button: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Configures the bottom-left menu button in Telegram."""
        return True

    def get_me(self) -> Optional[Dict[str, Any]]:
        """Retrieves bot account details."""
        return None

    @abstractmethod
    def get_updates(
        self, offset: Optional[int] = None, timeout: int = 30
    ) -> List[Dict[str, Any]]:
        """Polls for new updates from Telegram."""
        raise NotImplementedError
