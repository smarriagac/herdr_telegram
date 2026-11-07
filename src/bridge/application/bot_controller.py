"""Controller handling incoming Telegram events, commands, and callbacks."""

import html
import logging
import os
import re
from typing import Any, Dict, List, Optional

from bridge.application.agent_service import AgentBridgeService
from bridge.domain.ports import StateRepositoryPort, TelegramPort

logger = logging.getLogger("herdr-bridge.controller")

PERSISTENT_KEYBOARD = {
    "keyboard": [
        [{"text": "🤖 Mis Agentes"}, {"text": "📱 Mini App"}],
        [{"text": "📄 Ver Salida"}, {"text": "➕ Nuevo Agente"}],
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
        transcriber: Optional[Any] = None,
        tunnel: Optional[Any] = None,
    ):
        self.service = service
        self.topic_repo = topic_repo
        self.telegram = telegram
        self.allowed_chat_id = allowed_chat_id
        self.group_chat_id = group_chat_id
        self.transcriber = transcriber
        self.tunnel = tunnel

    def get_app_url(self) -> Optional[str]:
        """Resolves the live HTTPS URL for the Telegram Mini App."""
        if not self.tunnel:
            return None
        if hasattr(self.tunnel, "public_url"):
            return self.tunnel.public_url
        if callable(self.tunnel):
            return self.tunnel()
        return str(self.tunnel)

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

        if not self._is_authorized(chat_id, from_id):
            return

        # Check if message originated inside a dedicated project topic
        matched_workspace = None
        if chat_id == self.group_chat_id and thread_id:
            matched_workspace = self.topic_repo.get_workspace_by_thread_id(thread_id)

        # Handle voice notes and audio messages
        voice = msg.get("voice") or msg.get("audio")
        if voice:
            file_id = voice.get("file_id")
            if matched_workspace and file_id:
                self._handle_voice_prompt(chat_id, thread_id, matched_workspace, file_id)
                return
            elif file_id:
                self.telegram.send_message(
                    chat_id,
                    "⚠️ <i>Las notas de voz deben enviarse dentro del tema dedicado al proyecto (#📁 proyecto).</i>",
                    message_thread_id=thread_id,
                )
                return

        if not text:
            return

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
            resp, markup = self.service.build_status_reply(app_url=self.get_app_url())
            self.telegram.send_message(
                chat_id, resp, reply_markup=markup, message_thread_id=thread_id
            )
            return
        elif clean_lower in ("📱 mini app", "mini app", "app"):
            self._send_mini_app(chat_id, thread_id)
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
        elif clean_lower in ("🎯 ver resultado", "ver resultado", "resultado"):
            target = matched_workspace or "1"
            resp, markup = self.service.read_agent_result(target)
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
            resp, markup = self.service.build_status_reply(app_url=self.get_app_url())
            self.telegram.send_message(
                chat_id, resp, reply_markup=markup, message_thread_id=thread_id
            )
        elif cmd in ("/app", "/miniapp", "/web"):
            self._send_mini_app(chat_id, thread_id)
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
        elif cmd in ("/result", "/res"):
            target = args[0] if args else (matched_workspace or "1")
            lines = int(args[1]) if len(args) > 1 and args[1].isdigit() else 120
            resp, markup = self.service.read_agent_result(target, lines=lines)
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
            text, markup = self.service.build_status_reply(app_url=self.get_app_url())
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

        elif action == "quick":
            sub = parts[2] if len(parts) > 2 else ""
            target_agent = parts[3] if len(parts) > 3 else target
            prompts = {
                "test": "Ejecutá la suite de tests del proyecto y reportá el resultado.",
                "diff": "Mostrame las diferencias de git actuales con git diff --stat y git status.",
                "push": "Hacé commit con conventional commits de los cambios pendientes y subilos con git push.",
                "status": "Revisá el estado general del proyecto con git status.",
            }
            prompt_text = prompts.get(sub)
            if prompt_text and target_agent:
                self.telegram.answer_callback_query(cq_id, f"Iniciando {sub}...")
                resp = self.service.send_prompt(target_agent, prompt_text)
                self.telegram.send_message(
                    chat_id, resp, message_thread_id=thread_id
                )
            else:
                self.telegram.answer_callback_query(cq_id, "Acción rápida no disponible")

        elif action in ("result", "result_reload") and target:
            self.telegram.answer_callback_query(cq_id, "Cargando resultado...")
            text, markup = self.service.read_agent_result(target)
            if action == "result_reload" and msg_id:
                self.telegram.edit_message_text(
                    chat_id, msg_id, text, reply_markup=markup
                )
            else:
                self.telegram.send_message(
                    chat_id, text, reply_markup=markup, message_thread_id=thread_id
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

    def _handle_voice_prompt(
        self, chat_id: int, thread_id: Optional[int], target: str, file_id: str
    ):
        """Processes an incoming voice message, transcribes it, and dispatches as prompt."""
        if not self.transcriber or not self.transcriber.is_configured:
            msg = (
                "🎙️ <b>Nota de voz recibida</b>\n\n"
                "Para transcribir notas de voz automáticamente en tiempo real (en ~300ms y gratis), "
                "agregá tu clave de Groq en <code>~/.config/herdr-telegram/config.json</code>:\n"
                '<code>"groq_api_key": "gsk_..."</code>'
            )
            self.telegram.send_message(chat_id, msg, message_thread_id=thread_id)
            return

        status_msg = self.telegram.send_message(
            chat_id, "🎙️ <i>Transcribiendo nota de voz...</i>", message_thread_id=thread_id
        )
        status_msg_id = (
            status_msg.get("result", {}).get("message_id") if status_msg else None
        )

        file_info = self.telegram.get_file(file_id)
        file_path = file_info.get("file_path") if file_info else None
        if not file_path:
            if status_msg_id:
                self.telegram.edit_message_text(
                    chat_id, status_msg_id, "❌ Error al obtener el archivo de audio de Telegram."
                )
            return

        audio_bytes = self.telegram.download_file(file_path)
        if not audio_bytes:
            if status_msg_id:
                self.telegram.edit_message_text(
                    chat_id, status_msg_id, "❌ Error al descargar el audio de Telegram."
                )
            return

        ok, transcribed_text = self.transcriber.transcribe(
            audio_bytes, filename="voice.ogg"
        )
        if not ok or not transcribed_text.strip():
            if status_msg_id:
                self.telegram.edit_message_text(
                    chat_id, status_msg_id, f"❌ {transcribed_text}"
                )
            return

        if status_msg_id:
            self.telegram.edit_message_text(
                chat_id,
                status_msg_id,
                f"🎙️ <i>\"{html.escape(transcribed_text)}\"</i>\n\n⚡ <b>Enviando orden a {html.escape(target)}...</b>",
            )

        resp = self.service.send_prompt(target, transcribed_text)
        self.telegram.send_message(chat_id, resp, message_thread_id=thread_id)

    def _send_mini_app(self, chat_id: int, thread_id: Optional[int]):
        app_url = self.get_app_url()
        if app_url:
            msg = (
                "╭─ 📱 <b>Herdr Mini App</b>\n"
                "╰──────────────────────────\n\n"
                "Panel táctil interactivo para monitorear agentes, ver terminales y enviar órdenes en tiempo real."
            )
            markup = {
                "inline_keyboard": [
                    [{"text": "🚀 Abrir Mini App", "web_app": {"url": app_url}}],
                    [{"text": "🔄 Actualizar Panel", "callback_data": "act|refresh"}],
                ]
            }
            self.telegram.send_message(
                chat_id, msg, reply_markup=markup, message_thread_id=thread_id
            )
        else:
            self.telegram.send_message(
                chat_id,
                "⏳ <i>El túnel seguro HTTPS para la Mini App se está iniciando o no está disponible todavía. Intentá de nuevo en unos momentos o usá /status.</i>",
                message_thread_id=thread_id,
            )

    def _build_help_text(self) -> str:
        return (
            "╭─ 🤖 <b>Herdr Telegram Bridge — Ayuda</b>\n"
            "╰──────────────────────────\n\n"
            "📱 <b>Mini App Web (TMA):</b>\n"
            "• <code>/app</code>: Abrir la Mini App visual interactiva dentro de Telegram.\n\n"
            "💬 <b>En Temas Dedicados (#📁 proyecto):</b>\n"
            "• Escribí directamente cualquier texto para enviarlo como prompt al agente.\n"
            "• <code>/result</code>: Ver el resultado final o resumen del agente.\n"
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
