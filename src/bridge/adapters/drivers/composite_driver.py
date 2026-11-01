"""Composite Herdr Driver providing seamless dual-backend routing."""

import logging
from typing import List, Optional, Tuple

from bridge.domain.models import AgentInfo
from bridge.domain.ports import HerdrDriverPort

logger = logging.getLogger("herdr-bridge.composite")


class CompositeHerdrDriver(HerdrDriverPort):
    """Orchestrates both Herdr Classic and Herdr Desktop/Core backends."""

    def __init__(
        self,
        classic_driver: HerdrDriverPort,
        app_driver: HerdrDriverPort,
        preferred_mode: str = "auto",  # 'auto', 'classic', 'app'
    ):
        self.classic_driver = classic_driver
        self.app_driver = app_driver
        self.preferred_mode = preferred_mode.lower()

    @property
    def name(self) -> str:
        return f"composite({self.preferred_mode})"

    def is_available(self) -> bool:
        if self.preferred_mode == "classic":
            return self.classic_driver.is_available()
        elif self.preferred_mode == "app":
            return self.app_driver.is_available()
        return self.classic_driver.is_available() or self.app_driver.is_available()

    def list_agents(self) -> Tuple[Optional[List[AgentInfo]], Optional[str]]:
        all_agents: List[AgentInfo] = []
        errors: List[str] = []

        # 1. Fetch from Classic driver if enabled
        if self.preferred_mode in ("auto", "classic"):
            agents_c, err_c = self.classic_driver.list_agents()
            if agents_c is not None:
                all_agents.extend(agents_c)
            elif err_c and self.preferred_mode == "classic":
                errors.append(f"Classic: {err_c}")

        # 2. Fetch from App driver if enabled
        if self.preferred_mode in ("auto", "app"):
            agents_a, err_a = self.app_driver.list_agents()
            if agents_a is not None:
                all_agents.extend(agents_a)
            elif err_a and self.preferred_mode == "app":
                errors.append(f"App: {err_a}")

        if not all_agents and errors:
            return None, " | ".join(errors)

        return all_agents, None

    def _resolve_driver_for_target(
        self, target_id: str
    ) -> Tuple[HerdrDriverPort, str]:
        """Resolves whether a target ID or name belongs to Classic or App driver."""
        target_clean = target_id.strip()

        # Check by target ID format
        if ":" in target_clean:
            return self.classic_driver, target_clean
        if target_clean.startswith("t") and target_clean[1:].isdigit():
            return self.app_driver, target_clean
        if target_clean.startswith("sp"):
            return self.app_driver, target_clean

        # Check existing agents list
        agents, _ = self.list_agents()
        if agents:
            # Exact match by ID
            for ag in agents:
                if ag.id.lower() == target_clean.lower():
                    drv = (
                        self.app_driver
                        if ag.backend == "app"
                        else self.classic_driver
                    )
                    return drv, ag.id

            # Match by workspace label or name
            for ag in agents:
                if target_clean.lower() in (
                    (ag.name or "").lower(),
                    ag.workspace_label.lower(),
                ):
                    drv = (
                        self.app_driver
                        if ag.backend == "app"
                        else self.classic_driver
                    )
                    return drv, ag.id

        # Fallback to preferred driver
        if self.preferred_mode == "app":
            return self.app_driver, target_clean
        elif self.preferred_mode == "classic":
            return self.classic_driver, target_clean

        # In auto mode, check which driver is available
        if self.app_driver.is_available():
            return self.app_driver, target_clean
        return self.classic_driver, target_clean

    def create_workspace(
        self,
        name: str,
        engine: str = "agy",
        folder: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Tuple[bool, str, Optional[str]]:
        if self.preferred_mode == "classic":
            return self.classic_driver.create_workspace(
                name, engine, folder, session_id
            )
        elif self.preferred_mode == "app":
            return self.app_driver.create_workspace(
                name, engine, folder, session_id
            )

        # In auto mode, prefer app driver if available, else classic
        if self.app_driver.is_available():
            ok, msg, sid = self.app_driver.create_workspace(
                name, engine, folder, session_id
            )
            if ok:
                return ok, msg, sid

        return self.classic_driver.create_workspace(
            name, engine, folder, session_id
        )

    def send_prompt(self, target_id: str, prompt_text: str) -> Tuple[bool, str]:
        driver, resolved_id = self._resolve_driver_for_target(target_id)
        return driver.send_prompt(resolved_id, prompt_text)

    def send_keys(self, target_id: str, keys: List[str]) -> Tuple[bool, str]:
        driver, resolved_id = self._resolve_driver_for_target(target_id)
        return driver.send_keys(resolved_id, keys)

    def read_terminal(self, target_id: str, lines: int = 25) -> Tuple[bool, str]:
        driver, resolved_id = self._resolve_driver_for_target(target_id)
        return driver.read_terminal(resolved_id, lines)

    def close_workspace(self, target_id: str) -> Tuple[bool, str]:
        driver, resolved_id = self._resolve_driver_for_target(target_id)
        return driver.close_workspace(resolved_id)

    def rename_workspace(self, target_id: str, new_name: str) -> Tuple[bool, str]:
        driver, resolved_id = self._resolve_driver_for_target(target_id)
        return driver.rename_workspace(resolved_id, new_name)
