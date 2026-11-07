"""Cloudflare Tunnel adapter managing background quick tunnels for Telegram Mini App."""

import logging
import os
import re
import shutil
import subprocess
import threading
import time
from typing import Optional

logger = logging.getLogger("herdr-bridge.tunnel")


class CloudflareTunnel:
    """Spawns and manages a Cloudflare Quick Tunnel to expose the local HTTP API to Telegram."""

    def __init__(
        self,
        local_port: int = 8765,
        cloudflared_bin: Optional[str] = None,
    ):
        self.local_port = local_port
        self.cloudflared_bin = (
            cloudflared_bin
            or shutil.which("cloudflared")
            or os.path.expanduser("~/.local/bin/cloudflared")
        )
        self.public_url: Optional[str] = None
        self._process: Optional[subprocess.Popen] = None
        self._reader_thread: Optional[threading.Thread] = None
        self._url_ready_event = threading.Event()

    @property
    def is_available(self) -> bool:
        """Checks if cloudflared binary is installed and executable."""
        return bool(self.cloudflared_bin and os.path.isfile(self.cloudflared_bin))

    def start(self, timeout: float = 15.0) -> Optional[str]:
        """Starts the quick tunnel and waits for the public HTTPS URL to be assigned."""
        if not self.is_available:
            logger.warning(
                "cloudflared is not installed. Mini App local tunnel cannot be started automatically."
            )
            return None

        if self._process and self._process.poll() is None:
            return self.public_url

        self._url_ready_event.clear()
        cmd = [
            self.cloudflared_bin,
            "tunnel",
            "--url",
            f"http://127.0.0.1:{self.local_port}",
        ]

        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except Exception as e:
            logger.error("Failed to spawn cloudflared: %s", e)
            return None

        self._reader_thread = threading.Thread(
            target=self._read_tunnel_output,
            name="CloudflareTunnelReader",
            daemon=True,
        )
        self._reader_thread.start()

        # Wait until the URL is captured from output
        if self._url_ready_event.wait(timeout=timeout):
            logger.info("Cloudflare Tunnel active at: %s", self.public_url)
            return self.public_url

        logger.warning("Timed out waiting for Cloudflare Tunnel public URL.")
        return None

    def _read_tunnel_output(self):
        url_regex = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")
        if not self._process or not self._process.stderr:
            return

        try:
            for line in iter(self._process.stderr.readline, ""):
                if not line:
                    break
                m = url_regex.search(line)
                if m and not self.public_url:
                    self.public_url = m.group(0)
                    self._url_ready_event.set()
        except Exception as e:
            logger.debug("Tunnel reader closed: %s", e)

    def stop(self):
        """Terminates the tunnel process."""
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=3)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
            self._process = None
        self.public_url = None
        logger.info("Cloudflare Tunnel stopped.")
