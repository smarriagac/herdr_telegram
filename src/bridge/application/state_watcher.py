"""Background State Watcher monitoring agent execution and dispatching notifications."""

import html
import logging
import threading
import time
from typing import Dict, Optional, Set

from bridge.application.agent_service import AgentBridgeService
from bridge.domain.models import STATUS_CONFIG, AgentInfo
from bridge.domain.ports import HerdrDriverPort, StateRepositoryPort, TelegramPort

logger = logging.getLogger("herdr-bridge.watcher")


class StateWatcher:
    """Monitors active processes and pushes state transitions and approval buttons."""

    def __init__(
        self,
        service: AgentBridgeService,
        driver: HerdrDriverPort,
        topic_repo: StateRepositoryPort,
        telegram: TelegramPort,
        poll_interval: float = 2.5,
    ):
        self.service = service
        self.driver = driver
        self.topic_repo = topic_repo
        self.telegram = telegram
        self.poll_interval = poll_interval
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop, name="StateWatcherThread", daemon=True
        )
        self._thread.start()
        logger.info("State watcher thread started.")

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
            logger.info("State watcher thread stopped.")

    def _run_loop(self):
        known_states: Dict[str, str] = {}
        time.sleep(2)

        while not self._stop_event.is_set():
            try:
                agents, err = self.driver.list_agents()
                if agents is not None:
                    current_pids: Set[str] = set()
                    for ag in agents:
                        pid = ag.id
                        st = ag.status
                        ws_label = ag.workspace_label or pid
                        current_pids.add(pid)

                        # Sync session ID and ensure topic exists
                        thread_id = self.service.ensure_topic_for_workspace(
                            ws_label,
                            session_id=ag.session_id,
                            engine=ag.engine,
                            backend=ag.backend,
                        )
                        target_chat = (
                            self.service.group_chat_id
                            if self.service.group_chat_id
                            else self.service.allowed_chat_id
                        )

                        # Check for state transition
                        if pid in known_states:
                            old_st = known_states[pid]
                            if old_st != st:
                                self._handle_state_transition(
                                    ag, old_st, st, target_chat, thread_id
                                )
                        known_states[pid] = st

                    # Cleanup finished agents from known_states
                    for stale in list(known_states.keys()):
                        if stale not in current_pids:
                            del known_states[stale]

            except Exception as e:
                logger.error("Error in state watcher loop: %s", e)

            self._stop_event.wait(self.poll_interval)

    def _handle_state_transition(
        self,
        agent: AgentInfo,
        old_status: str,
        new_status: str,
        chat_id: int,
        thread_id: Optional[int],
    ):
        new_info = STATUS_CONFIG.get(new_status, STATUS_CONFIG["unknown"])
        old_info = STATUS_CONFIG.get(old_status, STATUS_CONFIG["unknown"])
        display_name = agent.display_name or agent.id
        btn_label = agent.name or agent.workspace_label or agent.id

        backend_tag = "[Desktop]" if agent.backend == "app" else "[Terminal]"

        msg = (
            f"╭─ 🔔 <b>Actualización de Estado</b> <code>{backend_tag}</code>\n"
            f"│  📁 Proyecto: <b>{html.escape(display_name)}</b>\n"
            f"│  Transición: {old_info['icon']} ➔ <b>{new_info['icon']} {new_info['label']}</b>\n"
            f"╰──────────────────────────"
        )
        markup = None

        if new_status == "blocked":
            ok, out = self.driver.read_terminal(agent.id, lines=10)
            if ok and out.strip():
                clean_out = html.escape(out.strip())
                msg += f"\n\n❓ <b>Esperando respuesta:</b>\n<pre>{clean_out}</pre>"

            markup = {
                "inline_keyboard": [
                    [
                        {
                            "text": f"✅ Aceptar ({btn_label})",
                            "callback_data": f"act|enter|{agent.id}",
                        },
                        {"text": "👍 Sí", "callback_data": f"act|yes|{agent.id}"},
                        {"text": "❌ Cancelar", "callback_data": f"act|esc|{agent.id}"},
                    ],
                    [
                        {
                            "text": "📄 Ver más líneas",
                            "callback_data": f"act|read|{agent.id}",
                        },
                        {"text": "📋 Panel Principal", "callback_data": "act|refresh"},
                    ],
                ]
            }
        elif new_status in ("idle", "done") and old_status == "working":
            msg += "\n\n🎉 <i>¡El agente completó la tarea asignada!</i>"
            markup = {
                "inline_keyboard": [
                    [
                        {
                            "text": f"📄 Ver resultado [{btn_label}]",
                            "callback_data": f"act|read|{agent.id}",
                        }
                    ]
                ]
            }

        self.telegram.send_message(
            chat_id,
            msg,
            reply_markup=markup,
            message_thread_id=thread_id,
        )
