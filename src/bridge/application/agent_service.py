"""Application service orchestrating AI agent and workspace operations."""

import html
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from bridge.application.terminal_formatter import (
    clean_terminal_output,
    extract_agent_result,
    format_telegram_markdown,
    safe_truncate_html,
)
from bridge.domain.models import STATUS_CONFIG, AgentInfo, TopicBinding
from bridge.domain.ports import HerdrDriverPort, StateRepositoryPort, TelegramPort

logger = logging.getLogger("herdr-bridge.service")


class AgentBridgeService:
    """Core application service managing agents, topics, and sessions."""

    def __init__(
        self,
        driver: HerdrDriverPort,
        topic_repo: StateRepositoryPort,
        telegram: TelegramPort,
        allowed_chat_id: int,
        group_chat_id: Optional[int] = None,
        projects_dir: str = "~/proyectos",
    ):
        self.driver = driver
        self.topic_repo = topic_repo
        self.telegram = telegram
        self.allowed_chat_id = allowed_chat_id
        self.group_chat_id = group_chat_id
        self.projects_dir = os.path.expanduser(projects_dir)

    def ensure_topic_for_workspace(
        self,
        workspace_name: str,
        session_id: Optional[str] = None,
        engine: str = "agy",
        backend: str = "auto",
    ) -> Optional[int]:
        """Ensures a Telegram forum topic exists for the workspace."""
        if not self.group_chat_id:
            return None

        binding = self.topic_repo.get_topic_by_workspace(workspace_name)
        if binding and binding.thread_id:
            if session_id and binding.session_id != session_id:
                binding.session_id = session_id
                self.topic_repo.save_topic(binding)
            return binding.thread_id

        # Create topic in Telegram
        thread_id = self.telegram.create_forum_topic(
            self.group_chat_id, workspace_name
        )
        if thread_id:
            new_binding = TopicBinding(
                workspace_name=workspace_name,
                thread_id=thread_id,
                session_id=session_id,
                engine=engine,
                backend=backend,
            )
            self.topic_repo.save_topic(new_binding)

            # Send welcome message inside the new topic
            welcome_text = (
                f"╭─ 🚀 <b>Tema Vinculado: {html.escape(workspace_name)}</b>\n"
                f"│  Motor: <code>{html.escape(engine)}</code>\n"
                f"│  Origen: <b>{backend.upper()}</b>\n"
                f"╰──────────────────────────\n\n"
                "💬 <b>Podés chatear directamente acá:</b> cualquier mensaje que escribas "
                "se inyectará automáticamente como prompt a este agente.\n\n"
                "💡 <i>Controles táctiles disponibles:</i>\n"
                "• <code>/enter</code>: Confirmar selección\n"
                "• <code>/yes</code>: Responder Sí (y + Enter)\n"
                "• <code>/esc</code>: Cancelar diálogo\n"
                "• <code>/read</code>: Ver terminal"
            )
            welcome_markup = {
                "inline_keyboard": [
                    [
                        {"text": "🧪 Tests", "callback_data": f"act|quick|test|{workspace_name}"},
                        {"text": "📊 Git Diff", "callback_data": f"act|quick|diff|{workspace_name}"},
                        {"text": "🛑 Abortar", "callback_data": f"act|esc|{workspace_name}"},
                    ],
                    [
                        {"text": "🎯 Ver Resultado", "callback_data": f"act|result|{workspace_name}"},
                        {"text": "📄 Ver Terminal", "callback_data": f"act|read|{workspace_name}"},
                    ],
                ]
            }
            self.telegram.send_message(
                self.group_chat_id,
                welcome_text,
                reply_markup=welcome_markup,
                message_thread_id=thread_id,
            )
            return thread_id
        return None

    def build_status_reply(self) -> Tuple[str, Dict[str, Any]]:
        """Constructs an interactive status dashboard of all running agents."""
        agents, err = self.driver.list_agents()
        if agents is None:
            return (
                f"⚠️ <b>Error al consultar agentes:</b>\n<code>{html.escape(str(err))}</code>",
                {"inline_keyboard": [[{"text": "🔄 Reintentar", "callback_data": "act|refresh"}]]},
            )

        if not agents:
            return (
                "🤖 <b>No hay agentes activos en ejecución.</b>\n\n"
                "Podés iniciar uno tocando <b>➕ Nuevo Agente</b> o con <code>/new &lt;nombre&gt;</code>.",
                {
                    "inline_keyboard": [
                        [
                            {"text": "➕ Nuevo Agente", "callback_data": "act|quick_new"},
                            {"text": "🔄 Actualizar", "callback_data": "act|refresh"},
                        ]
                    ]
                },
            )

        topics = self.topic_repo.load_topics()
        lines = [f"🤖 <b>Agentes Activos ({len(agents)})</b>\n"]
        buttons: List[List[Dict[str, str]]] = []

        for ag in agents:
            st = ag.status
            info = STATUS_CONFIG.get(st, STATUS_CONFIG["unknown"])
            target_id = ag.id
            ws_label = ag.workspace_label or ag.id
            btn_label = ag.name or ws_label

            backend_tag = "[Desktop]" if ag.backend == "app" else "[Terminal]"

            card = [
                f"╭─ {info['icon']} <b>{html.escape(ag.display_name)}</b> <code>{backend_tag}</code>",
                f"│  Estado: <b>{info['label']}</b>",
                f"│  Motor: <code>{html.escape(ag.engine)}</code> · ID: <code>{html.escape(target_id)}</code>",
            ]

            topic = topics.get(ws_label)
            if topic and topic.session_id:
                short_sess = topic.session_id[:8] + "…"
                card.append(f"│  Sesión: <code>{html.escape(short_sess)}</code>")

            card.append("╰──────────────────────────")
            lines.append("\n".join(card))

            # Interactive touch buttons per agent
            agent_row = [
                {"text": f"📄 Salida [{btn_label}]", "callback_data": f"act|read|{target_id}"},
                {"text": f"💬 Orden", "callback_data": f"act|prompt|{target_id}"},
            ]
            if st == "blocked":
                agent_row.insert(0, {"text": "✅ Aceptar", "callback_data": f"act|enter|{target_id}"})
                agent_row.insert(1, {"text": "❌ Cancelar", "callback_data": f"act|esc|{target_id}"})
            buttons.append(agent_row)

        buttons.append([
            {"text": "➕ Nuevo Agente", "callback_data": "act|quick_new"},
            {"text": "🔄 Actualizar", "callback_data": "act|refresh"},
        ])

        return "\n\n".join(lines), {"inline_keyboard": buttons}

    def create_agent(
        self, name: str, engine: str = "agy"
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        """Creates a project folder, launches workspace, and binds Telegram topic."""
        clean_name = re.sub(r"[^a-zA-Z0-9_\-]", "", name).strip()
        if not clean_name:
            return "❌ Nombre inválido. Usá letras, números o guiones.", None

        folder = os.path.join(self.projects_dir, clean_name)
        os.makedirs(folder, exist_ok=True)

        ok, msg, session_id = self.driver.create_workspace(
            clean_name, engine=engine, folder=folder
        )
        if not ok:
            return f"❌ <b>Error al crear espacio:</b>\n{html.escape(msg)}", None

        # Bind topic in supergroup
        thread_id = self.ensure_topic_for_workspace(
            clean_name, session_id=session_id, engine=engine
        )

        resp = (
            f"🚀 <b>Agente '{html.escape(clean_name)}' iniciado con éxito.</b>\n\n"
            f"📁 Carpeta: <code>{html.escape(folder)}</code>\n"
            f"⚙️ Motor: <code>{html.escape(engine)}</code>"
        )
        if thread_id:
            resp += f"\n📌 Tema asignado en el Supergrupo: #📁 {html.escape(clean_name)}"

        return resp, None

    def resume_agent(self, name: str) -> Tuple[str, Optional[Dict[str, Any]]]:
        """Resumes an existing agent restoring historical conversation context."""
        clean_name = name.strip()
        topic = self.topic_repo.get_topic_by_workspace(clean_name)
        session_id = topic.session_id if topic else None
        engine = topic.engine if topic else "agy"
        folder = os.path.join(self.projects_dir, clean_name)

        ok, msg, new_session = self.driver.create_workspace(
            clean_name, engine=engine, folder=folder, session_id=session_id
        )
        if not ok:
            return f"❌ <b>Error al reanudar:</b>\n{html.escape(msg)}", None

        if new_session and topic:
            self.topic_repo.update_session_id(clean_name, new_session)

        info_text = f"🔄 <b>Agente '{html.escape(clean_name)}' reanudado con éxito.</b>"
        if session_id:
            info_text += f"\n💾 <i>Historial restaurado desde sesión:</i> <code>{html.escape(session_id[:8])}…</code>"

        return info_text, None

    def send_prompt(self, target: str, prompt_text: str) -> str:
        """Sends a natural language prompt to the agent."""
        clean_prompt = prompt_text.strip()
        if not clean_prompt:
            return "❌ El mensaje no puede estar vacío."

        ok, msg = self.driver.send_prompt(target, clean_prompt)
        if ok:
            return f"💬 <b>Orden enviada a {html.escape(target)}:</b>\n<i>\"{html.escape(clean_prompt)}\"</i>"
        return f"❌ <b>Error enviando orden:</b>\n{html.escape(msg)}"

    def send_quick_key(self, target: str, key_name: str) -> Tuple[bool, str]:
        """Sends key sequence to the target agent."""
        key_map = {
            "enter": ["enter"],
            "yes": ["y", "enter"],
            "esc": ["esc"],
        }
        keys = key_map.get(key_name.lower(), [key_name])
        return self.driver.send_keys(target, keys)

    def _resolve_agent_context(
        self, target: str
    ) -> Tuple[str, str, str, str, str]:
        """Resolves target agent into (display_name, status_icon, status_label, engine, backend_tag)."""
        target_clean = target.strip()
        agents, _ = self.driver.list_agents()
        if agents:
            for ag in agents:
                if target_clean in (ag.id, ag.workspace_label, ag.name, ag.workspace_id):
                    st = ag.status
                    info = STATUS_CONFIG.get(st, STATUS_CONFIG["unknown"])
                    backend_tag = "[Desktop]" if ag.backend == "app" else "[Terminal]"
                    return (
                        ag.display_name or ag.workspace_label or ag.id,
                        info["icon"],
                        info["label"],
                        ag.engine,
                        backend_tag,
                    )

        # Fallback to topic repository
        topic = self.topic_repo.get_topic_by_workspace(target_clean)
        if topic:
            backend_tag = (
                f"[{topic.backend.title()}]" if topic.backend != "auto" else ""
            )
            return (
                target_clean,
                "💤",
                "En espera",
                topic.engine,
                backend_tag,
            )

        return (target_clean, "❓", "Desconocido", "agy", "")

    def read_agent_result(
        self, target: str, lines: int = 120
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        """Reads recent agent output and formats the meaningful result for Telegram."""
        display_name, icon, status_label, engine, backend_tag = (
            self._resolve_agent_context(target)
        )
        ok, out = self.driver.read_terminal(target, lines=lines)
        if not ok or not out.strip():
            header = (
                f"╭─ 🎯 <b>Resultado: {html.escape(display_name)}</b>"
                + (f" <code>{backend_tag}</code>\n" if backend_tag else "\n")
                + f"│  Estado: {icon} <b>{status_label}</b> · Motor: <code>{html.escape(engine)}</code>\n"
                f"╰──────────────────────────\n\n"
            )
            return (
                f"{header}📄 <i>No hay salida reciente ni resultado disponible para este agente.</i>",
                {
                    "inline_keyboard": [
                        [
                            {
                                "text": "🔄 Recargar",
                                "callback_data": f"act|result_reload|{target}",
                            },
                            {
                                "text": "📋 Panel Principal",
                                "callback_data": "act|refresh",
                            },
                        ]
                    ]
                },
            )

        # Extract the substantive result and format it safely for Telegram
        extracted = extract_agent_result(out)
        formatted_body = format_telegram_markdown(extracted)

        header = (
            f"╭─ 🎯 <b>Resultado: {html.escape(display_name)}</b>"
            + (f" <code>{backend_tag}</code>\n" if backend_tag else "\n")
            + f"│  Estado: {icon} <b>{status_label}</b> · Motor: <code>{html.escape(engine)}</code>\n"
            f"╰──────────────────────────\n\n"
        )

        full_message = safe_truncate_html(header + formatted_body, max_chars=3900)

        markup = {
            "inline_keyboard": [
                [
                    {
                        "text": "🔄 Recargar",
                        "callback_data": f"act|result_reload|{target}",
                    },
                    {
                        "text": "💬 Nueva Orden",
                        "callback_data": f"act|prompt|{target}",
                    },
                ],
                [
                    {
                        "text": "🧪 Tests",
                        "callback_data": f"act|quick|test|{target}",
                    },
                    {
                        "text": "📊 Git Diff",
                        "callback_data": f"act|quick|diff|{target}",
                    },
                    {
                        "text": "🛑 Abortar",
                        "callback_data": f"act|esc|{target}",
                    },
                ],
                [
                    {
                        "text": "🖥️ Terminal Cruda",
                        "callback_data": f"act|read|{target}",
                    },
                    {
                        "text": "📋 Panel Principal",
                        "callback_data": "act|refresh",
                    },
                ],
            ]
        }
        return full_message, markup

    def read_terminal(
        self, target: str, lines: int = 30
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        """Reads recent terminal output and returns formatted HTML pre block."""
        display_name, _, _, _, _ = self._resolve_agent_context(target)
        ok, out = self.driver.read_terminal(target, lines=lines)
        if not ok or not out.strip():
            return (
                f"📄 <i>Terminal sin salida reciente para {html.escape(display_name)}.</i>",
                {
                    "inline_keyboard": [
                        [{"text": "🔄 Recargar", "callback_data": f"act|read_reload|{target}"}]
                    ]
                },
            )

        clean_out = clean_terminal_output(out)
        escaped_out = html.escape(clean_out)
        pre_block = safe_truncate_html(f"<pre>{escaped_out}</pre>", max_chars=3800)

        markup = {
            "inline_keyboard": [
                [
                    {"text": "🔄 Recargar", "callback_data": f"act|read_reload|{target}"},
                    {"text": "🎯 Ver Resultado", "callback_data": f"act|result|{target}"},
                ],
                [
                    {"text": "✅ Enter", "callback_data": f"act|enter|{target}"},
                    {"text": "❌ Cancelar", "callback_data": f"act|esc|{target}"},
                ],
                [
                    {"text": "📋 Panel Principal", "callback_data": "act|refresh"},
                ],
            ]
        }
        return (
            f"📄 <b>Salida de Terminal ({html.escape(display_name)}):</b>\n{pre_block}",
            markup,
        )

    def close_workspace(self, target: str) -> str:
        """Closes a workspace and archives its topic."""
        ok, msg = self.driver.close_workspace(target)
        if not ok:
            return f"❌ <b>Error cerrando espacio:</b>\n{html.escape(msg)}"

        topic = self.topic_repo.get_topic_by_workspace(target)
        if topic and topic.thread_id and self.group_chat_id:
            self.telegram.close_forum_topic(self.group_chat_id, topic.thread_id)
            self.topic_repo.delete_topic(target)

        return f"⏹️ <b>Espacio '{html.escape(target)}' cerrado correctamente.</b>"
