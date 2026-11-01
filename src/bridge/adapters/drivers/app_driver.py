"""Herdr App Driver (herdr-app desktop and herdr-core hc)."""

import json
import logging
import os
import subprocess
from typing import Any, Dict, List, Optional, Tuple

from bridge.domain.models import AgentInfo
from bridge.domain.ports import HerdrDriverPort

logger = logging.getLogger("herdr-bridge.app")


class HerdrAppDriver(HerdrDriverPort):
    """Driver for Herdr Desktop (herdr-app) and herdr-core (hc)."""

    def __init__(
        self,
        herdr_app_bin: str = "herdr-app",
        hc_bin: str = "hc",
        timeout: int = 25,
    ):
        self.herdr_app_bin = herdr_app_bin
        self.hc_bin = hc_bin
        self.timeout = timeout

    @property
    def name(self) -> str:
        return "app"

    def _run_cmd(
        self, cmd: List[str], timeout: Optional[int] = None
    ) -> Tuple[int, str, str]:
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
            return -1, "", "Timeout executing command"
        except Exception as e:
            return -1, "", str(e)

    def is_available(self) -> bool:
        # Check if hc or herdr-app executable exists and responds
        code, out, _ = self._run_cmd([self.hc_bin, "ls", "--json"], timeout=5)
        if code == 0:
            return True
        code_app, _, _ = self._run_cmd([self.herdr_app_bin, "status"], timeout=5)
        return code_app == 0

    def list_agents(self) -> Tuple[Optional[List[AgentInfo]], Optional[str]]:
        # 1. Fetch live terminals from hc
        code, out, err = self._run_cmd([self.hc_bin, "ls", "--json"])
        if code != 0:
            return None, err or "Error querying herdr-core (hc)"

        try:
            hc_data = json.loads(out)
            terminals = hc_data.get("terminals", [])
        except Exception as e:
            return None, f"JSON parse error from hc ls: {e}"

        # 2. Fetch spaces and tabs from herdr-app if available
        spaces_map: Dict[str, str] = {}
        tabs_map: Dict[str, str] = {}
        term_to_space: Dict[str, str] = {}
        term_to_tab: Dict[str, str] = {}

        code_app, out_app, _ = self._run_cmd(
            [self.herdr_app_bin, "ls"], timeout=5
        )
        if code_app == 0 and out_app:
            try:
                app_data = json.loads(out_app)
                for sp in app_data.get("spaces", []):
                    sp_id = sp.get("id")
                    sp_name = sp.get("name") or sp_id
                    spaces_map[sp_id] = sp_name
                    for tb in sp.get("tabs", []):
                        tb_id = tb.get("id")
                        tb_name = tb.get("name", "")
                        tabs_map[tb_id] = tb_name
                        for term in tb.get("terminals", []):
                            t_addr = term.get("terminal")
                            if t_addr:
                                term_to_space[t_addr] = sp_name
                                term_to_tab[t_addr] = tb_name
            except Exception:
                pass

        agents: List[AgentInfo] = []
        for t in terminals:
            addr = t.get("address", "")
            if not addr:
                continue

            # Query detailed terminal metadata from hc get <addr> --json
            code_det, out_det, _ = self._run_cmd(
                [self.hc_bin, "get", addr, "--json"], timeout=4
            )
            det = {}
            if code_det == 0 and out_det:
                try:
                    det = json.loads(out_det)
                except Exception:
                    det = {}

            labels = det.get("labels", {})
            sp_label = labels.get("herdr.space")
            tb_label = labels.get("herdr.tab")

            # Determine space name
            ws_label = (
                term_to_space.get(addr)
                or spaces_map.get(sp_label)
                or labels.get("where", "").split(" / ")[0]
                or det.get("title")
                or addr
            )

            # Determine tab name
            tb_name = term_to_tab.get(addr) or tabs_map.get(tb_label, "")

            # Determine agent status
            raw_status = det.get("status")
            state = det.get("state", "live")
            if state != "live":
                st = "stopped"
            elif raw_status in ("working", "idle", "blocked", "done", "error"):
                st = raw_status
            else:
                st = "idle"

            # Determine agent engine
            fg = det.get("foreground", {})
            engine = fg.get("name") or t.get("agent") or "bash"
            agent_name = det.get("name")

            # Determine session UUID if present in argv or env
            session_id = None
            argv = det.get("argv", []) + fg.get("argv", [])
            for i, arg in enumerate(argv):
                if arg == "--conversation" and i + 1 < len(argv):
                    session_id = argv[i + 1]
                    break

            agents.append(
                AgentInfo(
                    id=addr,
                    name=agent_name,
                    workspace_id=sp_label,
                    workspace_label=ws_label,
                    tab_id=tb_label,
                    tab_label=tb_name,
                    status=st,
                    session_id=session_id,
                    engine=engine,
                    backend="app",
                    raw_metadata=det or t,
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
        target_folder = folder or os.path.expanduser("~/proyectos")
        argv_list = [engine]
        if session_id:
            argv_list.extend(["--conversation", session_id])

        # 1. Try launching through herdr-app window first if open
        argv_json = json.dumps(argv_list)
        code, out, err = self._run_cmd(
            [
                self.herdr_app_bin,
                "do",
                "space.new",
                "--name",
                name,
                "--folder",
                target_folder,
                "--argv",
                argv_json,
            ]
        )
        if code == 0:
            try:
                res_obj = json.loads(out)
                term_id = res_obj.get("terminal")
                return (
                    True,
                    f"Desktop space '{name}' created with terminal {term_id}.",
                    session_id,
                )
            except Exception:
                return (
                    True,
                    f"Desktop space '{name}' created successfully.",
                    session_id,
                )

        # 2. If herdr-app fails (e.g. window not running), fallback to hc run --bg
        hc_cmd = [
            self.hc_bin,
            "run",
            "--bg",
            "--name",
            name,
            "--cwd",
            target_folder,
        ] + argv_list
        code_hc, out_hc, err_hc = self._run_cmd(hc_cmd, timeout=35)
        if code_hc == 0:
            return (
                True,
                f"Agent '{name}' started in background terminal.",
                session_id,
            )

        return (
            False,
            f"Failed to create space/terminal: {err or err_hc or out_hc}",
            None,
        )

    def send_prompt(self, target_id: str, prompt_text: str) -> Tuple[bool, str]:
        # target_id is the terminal address (e.g., 't1', 't4')
        code, out, err = self._run_cmd(
            [self.hc_bin, "send", target_id, prompt_text]
        )
        if code == 0:
            return True, "Prompt delivered via herdr-core (hc)."
        return False, err or out or "Error sending prompt to terminal"

    def send_keys(self, target_id: str, keys: List[str]) -> Tuple[bool, str]:
        # Map common keys to hc keys command
        # hc keys <t> enter / esc / up / ctrl+c
        # If key is 'y', hc keys doesn't have bare 'y', so send 'y' via send or keys
        parsed_keys: List[str] = []
        for k in keys:
            lk = k.lower()
            if lk in ("enter", "esc", "up", "down", "left", "right", "ctrl+c"):
                parsed_keys.append(lk)
            elif lk == "y":
                # For yes, send 'y' character then enter
                self._run_cmd([self.hc_bin, "send", target_id, "y"])
                parsed_keys.append("enter")

        if not parsed_keys:
            parsed_keys = ["enter"]

        code, out, err = self._run_cmd(
            [self.hc_bin, "keys", target_id] + parsed_keys
        )
        if code == 0:
            return True, f"Keys sent via hc: {' '.join(parsed_keys)}"
        return False, err or out or "Error sending keys via hc"

    def read_terminal(self, target_id: str, lines: int = 25) -> Tuple[bool, str]:
        code, out, err = self._run_cmd(
            [self.hc_bin, "read", "--lines", str(lines), target_id]
        )
        if code == 0:
            return True, out
        return False, err or out or "Error reading terminal via hc"

    def close_workspace(self, target_id: str) -> Tuple[bool, str]:
        # If target_id is a space id (starts with 'sp'), close space via herdr-app
        if target_id.startswith("sp"):
            payload = json.dumps({"id": target_id, "confirmed": True})
            code, out, err = self._run_cmd(
                [self.herdr_app_bin, "do", "space.close", payload]
            )
            if code == 0:
                return True, f"Space '{target_id}' closed."
            return False, err or out or "Error closing space in herdr-app"

        # Otherwise terminate terminal via hc kill & rm
        code_k, out_k, err_k = self._run_cmd([self.hc_bin, "kill", target_id])
        self._run_cmd([self.hc_bin, "rm", target_id])
        if code_k == 0:
            return True, f"Terminal '{target_id}' terminated."
        return False, err_k or out_k or "Error killing terminal in hc"

    def rename_workspace(self, target_id: str, new_name: str) -> Tuple[bool, str]:
        if target_id.startswith("sp"):
            code, out, err = self._run_cmd(
                [
                    self.herdr_app_bin,
                    "do",
                    "space.rename",
                    "--id",
                    target_id,
                    "--name",
                    new_name,
                ]
            )
            if code == 0:
                return True, f"Space renamed to '{new_name}'."
            return False, err or out or "Error renaming space"

        code, out, err = self._run_cmd(
            [self.hc_bin, "label", target_id, f"name={new_name}"]
        )
        if code == 0:
            return True, f"Terminal labeled with name '{new_name}'."
        return False, err or out or "Error renaming terminal"
