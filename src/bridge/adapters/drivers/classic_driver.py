"""Classic Herdr Driver (herdr CLI / socket)."""

import json
import logging
import re
import subprocess
from typing import Any, Dict, List, Optional, Tuple

from bridge.domain.models import AgentInfo
from bridge.domain.ports import HerdrDriverPort

logger = logging.getLogger("herdr-bridge.classic")


class ClassicHerdrDriver(HerdrDriverPort):
    """Driver for Herdr Classic (v0.9 multiplexer CLI and herdr.sock)."""

    def __init__(self, herdr_bin: str = "herdr", timeout: int = 25):
        self.herdr_bin = herdr_bin
        self.timeout = timeout

    @property
    def name(self) -> str:
        return "classic"

    def _run_cmd(
        self, args: List[str], timeout: Optional[int] = None
    ) -> Tuple[int, str, str]:
        cmd = [self.herdr_bin] + args
        try:
            res = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout or self.timeout,
            )
            return res.returncode, res.stdout.strip(), res.stderr.strip()
        except subprocess.TimeoutExpired:
            return -1, "", "Timeout executing Herdr command"
        except Exception as e:
            return -1, "", str(e)

    def is_available(self) -> bool:
        code, out, _ = self._run_cmd(["status", "server"], timeout=5)
        return code == 0

    def list_agents(self) -> Tuple[Optional[List[AgentInfo]], Optional[str]]:
        code, out, err = self._run_cmd(["agent", "list"])
        if code != 0 or not out:
            return None, err or "Error listing Herdr classic agents"

        try:
            raw_agents = json.loads(out).get("result", {}).get("agents", [])
        except Exception as e:
            return None, f"JSON parse error from agent list: {e}"

        ws_map: Dict[str, str] = {}
        tab_map: Dict[str, str] = {}

        code_ws, out_ws, _ = self._run_cmd(["workspace", "list"])
        if code_ws == 0 and out_ws:
            try:
                for w in (
                    json.loads(out_ws).get("result", {}).get("workspaces", [])
                ):
                    ws_map[w.get("workspace_id")] = w.get("label")
            except Exception:
                pass

        code_tab, out_tab, _ = self._run_cmd(["tab", "list"])
        if code_tab == 0 and out_tab:
            try:
                for t in json.loads(out_tab).get("result", {}).get("tabs", []):
                    tab_map[t.get("tab_id")] = t.get("label")
            except Exception:
                pass

        agents: List[AgentInfo] = []
        for ag in raw_agents:
            pid = ag.get("pane_id", "")
            ws_id = ag.get("workspace_id")
            tab_id = ag.get("tab_id")
            ws_label = ws_map.get(ws_id, ws_id) or "workspace"
            tab_label = tab_map.get(tab_id, "")
            st = ag.get("agent_status", "unknown")
            engine = ag.get("agent", "agy")
            name = ag.get("name")
            session_id = ag.get("agent_session", {}).get("value")

            agents.append(
                AgentInfo(
                    id=pid,
                    name=name,
                    workspace_id=ws_id,
                    workspace_label=ws_label,
                    tab_id=tab_id,
                    tab_label=tab_label,
                    status=st,
                    session_id=session_id,
                    engine=engine,
                    backend="classic",
                    raw_metadata=ag,
                )
            )

        return agents, None

    def create_workspace(
        self,
        name: str,
        engine: str = "agy",
        folder: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Tuple[bool, str, Optional[str]]:
        code, out, err = self._run_cmd(["workspace", "new", name])
        if code != 0:
            return False, f"Failed to create workspace: {err or out}", None

        ws_id = None
        try:
            ws_data = json.loads(out).get("result", {}).get("workspace", {})
            ws_id = ws_data.get("workspace_id")
        except Exception:
            pass

        cmd = ["workspace", "run", name, engine]
        if session_id:
            cmd.extend(["--conversation", session_id])

        code_ag, out_ag, err_ag = self._run_cmd(cmd, timeout=35)
        if code_ag != 0:
            if ws_id:
                self._run_cmd(["workspace", "close", ws_id])
            return (
                False,
                f"Failed to launch agent in workspace: {err_ag or out_ag}",
                None,
            )

        detected_session = session_id
        if not detected_session:
            detected_session = self._find_session_for_workspace(name)

        return (
            True,
            f"Workspace '{name}' created with engine '{engine}'.",
            detected_session,
        )

    def _find_session_for_workspace(self, ws_name: str) -> Optional[str]:
        agents, _ = self.list_agents()
        if agents:
            for ag in agents:
                if (
                    ag.workspace_label.lower() == ws_name.lower()
                    and ag.session_id
                ):
                    return ag.session_id
        return None

    def send_prompt(self, target_id: str, prompt_text: str) -> Tuple[bool, str]:
        code, out, err = self._run_cmd(
            ["agent", "prompt", target_id, prompt_text]
        )
        if code == 0:
            return True, "Prompt delivered successfully."
        return False, err or out or "Error delivering prompt"

    def send_keys(self, target_id: str, keys: List[str]) -> Tuple[bool, str]:
        code, out, err = self._run_cmd(
            ["agent", "send-keys", target_id] + keys
        )
        if code == 0:
            return True, f"Keys sent: {' '.join(keys)}"
        return False, err or out or "Error sending keys"

    def read_terminal(self, target_id: str, lines: int = 25) -> Tuple[bool, str]:
        code, out, err = self._run_cmd(
            ["agent", "read", target_id, "--lines", str(lines), "--format", "text"]
        )
        if code == 0:
            return True, out
        return False, err or out or "Error reading terminal output"

    def close_workspace(self, target_id: str) -> Tuple[bool, str]:
        # target_id could be a workspace ID, workspace label, or pane_id
        ws_id = target_id
        if ":" in target_id:
            ws_id = target_id.split(":")[0]

        code, out, err = self._run_cmd(["workspace", "close", ws_id])
        if code == 0:
            return True, f"Workspace '{ws_id}' closed."
        return False, err or out or "Error closing workspace"

    def rename_workspace(self, target_id: str, new_name: str) -> Tuple[bool, str]:
        code, out, err = self._run_cmd(
            ["agent", "rename", target_id, new_name]
        )
        if code == 0:
            return True, f"Renamed to '{new_name}'."
        return False, err or out or "Error renaming"
