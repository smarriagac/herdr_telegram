"""Telegram API client using Python standard library."""

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from bridge.application.terminal_formatter import safe_truncate_html
from bridge.domain.ports import TelegramPort

logger = logging.getLogger("herdr-bridge.telegram")


class TelegramClient(TelegramPort):
    """Zero-dependency HTTP client for the Telegram Bot API."""

    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.base_url = f"https://api.telegram.org/bot{bot_token}"

    def _call_api(
        self, method: str, payload: Optional[Dict[str, Any]] = None, timeout: int = 35
    ) -> Optional[Dict[str, Any]]:
        url = f"{self.base_url}/{method}"
        headers = {"Content-Type": "application/json"}
        data = json.dumps(payload).encode("utf-8") if payload else None

        req = urllib.request.Request(url, data=data, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw)
        except urllib.error.HTTPError as e:
            try:
                body = e.read().decode("utf-8")
                err_data = json.loads(body)
                desc = err_data.get("description", "")
                if "message is not modified" in desc.lower():
                    return {"ok": False, "result": "not_modified"}
                logger.error("Telegram API HTTP %d for %s: %s", e.code, method, desc)
                return err_data
            except Exception:
                logger.error("Telegram API HTTP %d for %s", e.code, method)
                return None
        except Exception as e:
            logger.error("Network error calling Telegram API %s: %s", method, e)
            return None

    def send_message(
        self,
        chat_id: int,
        text: str,
        reply_markup: Optional[Dict[str, Any]] = None,
        message_thread_id: Optional[int] = None,
        parse_mode: str = "HTML",
    ) -> Optional[Dict[str, Any]]:
        # Enforce Telegram 4096 character limit safely
        if len(text) > 4000:
            if parse_mode == "HTML":
                text = safe_truncate_html(text, max_chars=3950)
            else:
                text = text[:3950] + "\n\n[Truncado...]"

        payload: Dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        if message_thread_id:
            payload["message_thread_id"] = message_thread_id

        return self._call_api("sendMessage", payload)

    def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: Optional[Dict[str, Any]] = None,
        parse_mode: str = "HTML",
    ) -> Optional[Dict[str, Any]]:
        if len(text) > 4000:
            if parse_mode == "HTML":
                text = safe_truncate_html(text, max_chars=3950)
            else:
                text = text[:3950] + "\n\n[Truncado...]"

        payload: Dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup

        return self._call_api("editMessageText", payload)

    def answer_callback_query(
        self,
        callback_query_id: str,
        text: Optional[str] = None,
        show_alert: bool = False,
    ) -> bool:
        payload: Dict[str, Any] = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
        if show_alert:
            payload["show_alert"] = show_alert

        res = self._call_api("answerCallbackQuery", payload, timeout=10)
        return bool(res and res.get("ok"))

    def create_forum_topic(
        self, chat_id: int, name: str, icon_custom_emoji_id: Optional[str] = None
    ) -> Optional[int]:
        payload: Dict[str, Any] = {
            "chat_id": chat_id,
            "name": f"📁 {name}" if not name.startswith("📁") else name,
        }
        if icon_custom_emoji_id:
            payload["icon_custom_emoji_id"] = icon_custom_emoji_id

        res = self._call_api("createForumTopic", payload)
        if res and res.get("ok"):
            return res.get("result", {}).get("message_thread_id")
        return None

    def close_forum_topic(self, chat_id: int, message_thread_id: int) -> bool:
        payload = {"chat_id": chat_id, "message_thread_id": message_thread_id}
        res = self._call_api("closeForumTopic", payload)
        return bool(res and res.get("ok"))

    def get_file(self, file_id: str) -> Optional[Dict[str, Any]]:
        res = self._call_api("getFile", {"file_id": file_id})
        if res and res.get("ok"):
            return res.get("result")
        return None

    def download_file(self, file_path: str) -> Optional[bytes]:
        url = f"https://api.telegram.org/file/bot{self.bot_token}/{file_path}"
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read()
        except Exception as e:
            logger.error("Error downloading file %s: %s", file_path, e)
            return None

    def get_updates(
        self, offset: Optional[int] = None, timeout: int = 30
    ) -> List[Dict[str, Any]]:
        payload: Dict[str, Any] = {
            "timeout": timeout,
            "allowed_updates": ["message", "callback_query"],
        }
        if offset is not None:
            payload["offset"] = offset

        res = self._call_api("getUpdates", payload, timeout=timeout + 10)
        if res and res.get("ok"):
            return res.get("result", [])
        return []

    def set_my_commands(self, commands: List[Dict[str, str]]) -> bool:
        res = self._call_api("setMyCommands", {"commands": commands})
        return bool(res and res.get("ok"))
