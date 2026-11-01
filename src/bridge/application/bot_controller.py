"""Controller handling incoming Telegram events, commands, and callbacks."""

import html
import logging
import re
from typing import Any, Dict, List, Optional

from bridge.application.agent_service import AgentBridgeService
from bridge.domain.ports import StateRepositoryPort, TelegramPort

logger = logging.getLogger("herdr-bridge.controller")

PERSISTENT_KEYBOARD = {
    "keyboard": [
        [{"text": "🤖 Mis Agentes"}, {"text": "➕ Nuevo Agente"}],
        [{"text": "📄 Ver Salida"}, {"text": "❓ Ayuda / Comandos"}],
    ],
    "resize_keyboard": True,
    "persistent": True,
}


class BotController:
    """Dispatches Telegram updates to application services."""

    def __init__(
        self,
        service: AgentBridgeService,
        topic_repo: StateRepositoryPort,
        telegram: TelegramPort,
        allowed_chat_id: int,
        group_chat_id: Optional[int] = None,
    ):
        self.service = service
        self.topic_repo = topic_repo
        self.telegram = telegram
        self.allowed_chat_id = allowed_chat_id
        self.group_chat_id = group_chat_id

    def process_update(self, update: Dict[str, Any]):
        """Processes a single update object."""
        if "callback_query" in update:
            self._handle_callback_query(update["callback_query"])
        elif "message" in update:
            self._handle_message(update["message"])

    def _is_authorized(self, chat_id: int, from_id: int) -> bool:
        if chat_id != self.allowed_chat_id and chat_id != self.group_chat_id:
            return False
        # Whitelist personal chat ID (or Telegram service accounts)
        return from_id in (self.allowed_chat_id, 1087968824)

    def _handle_message(self, msg: Dict[str, Any]):
        chat = msg.get("chat", {})
        chat_id = chat.get("id")
        from_user = msg.get("from", {})
        from_id = from_user.get("id")
        thread_id = msg.get("message_thread_id")
        text = msg.get("text", "").strip()

        if not self._is_authorized(chat_id, from_id) or not text:
            return

        # Check if message originated inside a dedicated project topic
        matched_workspace = None
        if chat_id == self.group_chat_id and thread_id:
            matched_workspace = self.topic_repo.get_workspace_by_thread_id(thread_id)

        # 1. ForceReply Handling
        reply_to = msg.get("reply_to_message", {})
        if reply_to:
            orig = reply_to.get("text", "")
            if "Crear Nuevo Proyecto" in orig or "nombre de tu proyecto" in orig:
                resp, markup = self.service.create_agent(text)
                self.telegram.send_message(
                    chat_id, resp, reply_markup=markup, message_thread_id=thread_id
                )
                return

            if "Nueva orden para" in orig:
                m = re.search(r"Nueva orden para\s+([^:\n]+):", orig)
                if m:
                    target_cand = m.group(1).strip()
                    resp = self.service.send_prompt(target_cand, text)
                    self.telegram.send_message(
                        chat_id, resp, message_thread_id=thread_id
                    )
                    return

        # 2. Plain natural text inside a project topic -> direct prompt
        if matched_workspace and not text.startswith("/"):
            resp = self.service.send_prompt(matched_workspace, text)
            self.telegram.send_message(
                chat_id, resp, message_thread_id=thread_id
            )
            return

        # 3. Persistent keyboard triggers
        clean_lower = text.lower()
        if clean_lower in ("🤖 mis agentes", "mis agentes"):
            resp, markup = self.service.build_status_reply()
            self.telegram.send_message(
                chat_id, resp, reply_markup=markup, message_thread_id=thread_id
            )
            return
        elif clean_lower in ("➕ nuevo agente", "nuevo agente"):
            self._prompt_new_agent(chat_id, thread_id)
            return
        elif clean_lower in ("📄 ver salida", "ver salida"):
            target = matched_workspace or "1"
            resp, markup = self.service.read_terminal(target)
            self.telegram.send_message(
                chat_id, resp, reply_markup=markup, message_thread_id=thread_id
            )
            return
        elif clean_lower in ("❓ ayuda / comandos", "ayuda"):
            self.telegram.send_message(
                chat_id,
                self._build_help_text(),
                reply_markup=PERSISTENT_KEYBOARD,
                message_thread_id=thread_id,
            )
            return

        # 4. Slash commands
        parts = text.split()
        cmd = parts[0].lower().split("@")[0]
        args = parts[1:]

        if cmd in ("/start", "/help"):
            self.telegram.send_message(
                chat_id,
                self._build_help_text(),
                reply_markup=PERSISTENT_KEYBOARD,
                message_thread_id=thread_id,
            )
        elif cmd in ("/status", "/agents"):
            resp, markup = self.service.build_status_reply()
            self.telegram.send_message(
                chat_id, resp, reply_markup=markup, message_thread_id=thread_id
            )
        elif cmd == "/new":
            if not args:
                self._prompt_new_agent(chat_id, thread_id)
            else:
                engine = args[1] if len(args) > 1 else "agy"
                resp, markup = self.service.create_agent(args[0], engine=engine)
                self.telegram.send_message(
                    chat_id, resp, reply_markup=markup, message_thread_id=thread_id
                )
        elif cmd == "/resume":
            target = args[0] if args else matched_workspace
            if not target:
                self.telegram.send_message(
                    chat_id,
                    "⚠️ Indicá el nombre del proyecto: <code>/resume &lt;nombre&gt;</code>",
                    message_thread_id=thread_id,
                )
            else:
                resp, markup = self.service.resume_agent(target)
                self.telegram.send_message(
                    chat_id, resp, reply_markup=markup, message_thread_id=thread_id
                )
        elif cmd == "/read":
            target = args[0] if args else (matched_workspace or "1")
            lines = int(args[1]) if len(args) > 1 and args[1].isdigit() else 25
            resp, markup = self.service.read_terminal(target, lines=lines)
            self.telegram.send_message(
                chat_id, resp, reply_markup=markup, message_thread_id=thread_id
            )
        elif cmd == "/enter":
            target = args[0] if args else (matched_workspace or "1")
            ok, msg = self.service.send_quick_key(target, "enter")
            self.telegram.send_message(
                chat_id,
                f"✅ <b>Enter</b> enviado a <b>{html.escape(target)}</b>." if ok else f"❌ {msg}",
                message_thread_id=thread_id,
            )
        elif cmd == "/yes":
            target = args[0] if args else (matched_workspace or "1")
            ok, msg = self.service.send_quick_key(target, "yes")
            self.telegram.send_message(
                chat_id,
                f"👍 <b>Sí</b> (y + Enter) enviado a <b>{html.escape(target)}</b>." if ok else f"❌ {msg}",
                message_thread_id=thread_id,
            )
        elif cmd == "/esc":
            target = args[0] if args else (matched_workspace or "1")
            ok, msg = self.service.send_quick_key(target, "esc")
            self.telegram.send_message(
                chat_id,
                f"❌ <b>Escape</b> enviado a <b>{html.escape(target)}</b>." if ok else f"❌ {msg}",
                message_thread_id=thread_id,
            )
        elif cmd == "/close":
            target = args[0] if args else matched_workspace
            if not target:
                self.telegram.send_message(
                    chat_id,
                    "⚠️ Indicá el proyecto a cerrar: <code>/close &lt;nombre&gt;</code>",
                    message_thread_id=thread_id,
                )
            else:
                resp = self.service.close_workspace(target)
                self.telegram.send_message(
                    chat_id, resp, message_thread_id=thread_id
                )

    def _prompt_new_agent(self, chat_id: int, thread_id: Optional[int]):
        msg = (
            "╭─ ➕ <b>Crear Nuevo Proyecto</b>\n"
            "╰──────────────────────────\n\n"
            "Escribí el <b>nombre de tu proyecto</b> en la respuesta:"
        )
        self.telegram.send_message(
            chat_id,
            msg,
            reply_markup={"force_reply": True, "selective": True},
            message_thread_id=thread_id,
        )

    def _handle_callback_query(self, cq: Dict[str, Any]):
        cq_id = cq.get("id")
        data = cq.get("data", "")
        msg = cq.get("message", {})
        chat_id = msg.get("chat", {}).get("id")
        msg_id = msg.get("message_id")
        thread_id = msg.get("message_thread_id")
        from_id = cq.get("from", {}).get("id")

        if not self._is_authorized(chat_id, from_id):
            self.telegram.answer_callback_query(cq_id, "No autorizado", show_alert=True)
            return

        parts = data.split("|")
        action = parts[1] if len(parts) > 1 else ""
        target = parts[2] if len(parts) > 2 else ""

        if action == "refresh":
            self.telegram.answer_callback_query(cq_id, "Actualizando...")
            text, markup = self.service.build_status_reply()
            if msg_id:
                self.telegram.edit_message_text(
                    chat_id, msg_id, text, reply_markup=markup
                )

        elif action == "enter" and target:
            self.telegram.answer_callback_query(cq_id, "Enviando Enter...")
            ok, err = self.service.send_quick_key(target, "enter")
            self.telegram.send_message(
                chat_id,
                f"✅ <b>Enter</b> enviado a <b>{html.escape(target)}</b>." if ok else f"❌ Error: {err}",
                message_thread_id=thread_id,
            )

        elif action == "yes" and target:
            self.telegram.answer_callback_query(cq_id, "Enviando Sí...")
            ok, err = self.service.send_quick_key(target, "yes")
            self.telegram.send_message(
                chat_id,
                f"👍 <b>Sí</b> (y + Enter) enviado a <b>{html.escape(target)}</b>." if ok else f"❌ Error: {err}",
                message_thread_id=thread_id,
            )

        elif action == "esc" and target:
            self.telegram.answer_callback_query(cq_id, "Enviando Escape...")
            ok, err = self.service.send_quick_key(target, "esc")
            self.telegram.send_message(
                chat_id,
                f"❌ <b>Escape</b> enviado a <b>{html.escape(target)}</b>." if ok else f"❌ Error: {err}",
                message_thread_id=thread_id,
            )

        elif action in ("read", "read_reload") and target:
            self.telegram.answer_callback_query(cq_id, "Cargando salida...")
            text, markup = self.service.read_terminal(target, lines=25)
            if action == "read_reload" and msg_id:
                self.telegram.edit_message_text(
                    chat_id, msg_id, text, reply_markup=markup
                )
            else:
                self.telegram.send_message(
                    chat_id, text, reply_markup=markup, message_thread_id=thread_id
                )

        elif action == "prompt" and target:
            self.telegram.answer_callback_query(cq_id)
            prompt_text = (
                f"╭─ 💬 <b>Nueva orden para {html.escape(target)}:</b>\n"
                "╰──────────────────────────\n\n"
                "Escribí tu instrucción en la respuesta a este mensaje:"
            )
            self.telegram.send_message(
                chat_id,
                prompt_text,
                reply_markup={"force_reply": True, "selective": True},
                message_thread_id=thread_id,
            )

        elif action == "quick_new":
            self.telegram.answer_callback_query(cq_id)
            self._prompt_new_agent(chat_id, thread_id)

        else:
            self.telegram.answer_callback_query(cq_id)

    def _build_help_text(self) -> str:
        return (
            "╭─ 🤖 <b>Herdr Telegram Bridge — Ayuda</b>\n"
            "╰──────────────────────────\n\n"
            "💬 <b>En Temas Dedicados (#📁 proyecto):</b>\n"
            "• Escribí directamente cualquier texto para enviarlo como prompt al agente.\n"
            "• <code>/read</code>: Ver terminal reciente.\n"
            "• <code>/enter</code>: Confirmar (Enter).\n"
            "• <code>/yes</code>: Responder Sí (y + Enter).\n"
            "• <code>/esc</code>: Cancelar (Escape).\n"
            "• <code>/resume</code>: Reanudar sesión reteniendo contexto.\n"
            "• <code>/close</code>: Detener y archivar el proyecto.\n\n"
            "🌐 <b>Comandos Globales:</b>\n"
            "• <code>/status</code>: Dashboard de todos los agentes activos (Desktop y Terminal).\n"
            "• <code>/new &lt;nombre&gt; [motor]</code>: Crear nuevo proyecto (ej. <code>/new api agy</code>).\n"
            "• <code>/resume &lt;nombre&gt;</code>: Reanudar un agente existente con su session UUID.\n"
            "• <code>/read &lt;nombre&gt;</code>: Ver terminal de un agente específico."
        )
