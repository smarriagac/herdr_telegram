"""HTTP API server adapter serving REST endpoints and Mini App static assets."""

import html
import json
import logging
import mimetypes
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, unquote, urlparse

from bridge.application.agent_service import AgentBridgeService
from bridge.application.terminal_formatter import (
    clean_terminal_output,
    extract_agent_result,
    format_telegram_markdown,
)
from bridge.domain.models import STATUS_CONFIG
from bridge.domain.ports import StateRepositoryPort

logger = logging.getLogger("herdr-bridge.http")


class MiniAppHandler(BaseHTTPRequestHandler):
    """Request handler for Telegram Mini App REST API and static frontend assets."""

    server_service: AgentBridgeService
    server_topic_repo: StateRepositoryPort
    static_dir: str

    def log_message(self, format: str, *args: Any):
        logger.info("%s - " + format, self.address_string(), *args)

    def _send_json(self, status_code: int, data: Any):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, status_code: int, message: str):
        self._send_json(status_code, {"ok": False, "error": message})

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, HEAD")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        query = parse_qs(parsed.query)

        # 1. API: List all agents
        if path == "/api/agents":
            agents, err = self.server_service.driver.list_agents()
            if agents is None:
                self._send_error_json(500, str(err))
                return

            result_list = []
            for ag in agents:
                st = ag.status
                info = STATUS_CONFIG.get(st, STATUS_CONFIG["unknown"])
                result_list.append({
                    "id": ag.id,
                    "name": ag.name,
                    "workspace_label": ag.workspace_label,
                    "display_name": ag.display_name or ag.workspace_label or ag.id,
                    "status": st,
                    "status_label": info["label"],
                    "status_icon": info["icon"],
                    "engine": ag.engine,
                    "backend": ag.backend,
                    "session_id": ag.session_id,
                })
            self._send_json(200, {"ok": True, "agents": result_list})
            return

        # 2. API: Agent formatted result
        m_result = re.match(r"^/api/agents/([^/]+)/result$", path)
        if m_result:
            target = unquote(m_result.group(1))
            msg, _ = self.server_service.read_agent_result(target, lines=120)
            ok, raw_out = self.server_service.driver.read_terminal(target, lines=120)
            extracted = extract_agent_result(raw_out) if ok and raw_out else ""
            self._send_json(
                200,
                {
                    "ok": True,
                    "target": target,
                    "formatted_html": msg,
                    "result_text": extracted,
                },
            )
            return

        # 3. API: Agent terminal lines
        m_term = re.match(r"^/api/agents/([^/]+)/terminal$", path)
        if m_term:
            target = unquote(m_term.group(1))
            lines_param = query.get("lines", ["40"])[0]
            lines = int(lines_param) if lines_param.isdigit() else 40
            ok, out = self.server_service.driver.read_terminal(target, lines=lines)
            cleaned = clean_terminal_output(out) if ok and out else ""
            self._send_json(
                200,
                {
                    "ok": ok,
                    "target": target,
                    "output": cleaned,
                    "raw": out if ok else "",
                },
            )
            return

        # 4. Fallback to serving static SPA assets
        self._serve_static(parsed.path)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
        try:
            payload = json.loads(body) if body else {}
        except Exception:
            self._send_error_json(400, "Invalid JSON payload")
            return

        # 1. API: Send prompt to agent
        m_prompt = re.match(r"^/api/agents/([^/]+)/prompt$", path)
        if m_prompt:
            target = unquote(m_prompt.group(1))
            prompt_text = payload.get("prompt", "").strip()
            if not prompt_text:
                self._send_error_json(400, "Missing 'prompt' in payload")
                return
            resp = self.server_service.send_prompt(target, prompt_text)
            self._send_json(200, {"ok": True, "response": resp})
            return

        # 2. API: Send quick keys (enter, yes, esc)
        m_keys = re.match(r"^/api/agents/([^/]+)/keys$", path)
        if m_keys:
            target = unquote(m_keys.group(1))
            key_name = payload.get("key", "").strip()
            if not key_name:
                self._send_error_json(400, "Missing 'key' in payload")
                return
            ok, msg = self.server_service.send_quick_key(target, key_name)
            self._send_json(200, {"ok": ok, "message": msg})
            return

        # 3. API: Create new agent
        if path == "/api/agents/new":
            name = payload.get("name", "").strip()
            engine = payload.get("engine", "agy").strip()
            if not name:
                self._send_error_json(400, "Missing 'name' in payload")
                return
            resp, _ = self.server_service.create_agent(name, engine=engine)
            self._send_json(200, {"ok": True, "response": resp})
            return

        self._send_error_json(404, "Endpoint not found")

    def _serve_static(self, rel_path: str):
        clean_path = rel_path.lstrip("/")
        if not clean_path or clean_path == "/":
            clean_path = "index.html"

        file_path = os.path.join(self.static_dir, clean_path)

        # SPA fallback: if file does not exist, serve index.html
        if not os.path.isfile(file_path):
            file_path = os.path.join(self.static_dir, "index.html")

        if not os.path.isfile(file_path):
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Static assets not built yet. Run 'npm run build' in web/.")
            return

        mime_type, _ = mimetypes.guess_type(file_path)
        mime_type = mime_type or "application/octet-stream"

        with open(file_path, "rb") as f:
            content = f.read()

        self.send_response(200)
        self.send_header("Content-Type", mime_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(content)


def _resolve_static_dir(custom_path: Optional[str] = None) -> str:
    """Finds the web/dist directory across development and production layouts."""
    if custom_path and os.path.isdir(custom_path):
        return custom_path
    if "HERDR_STATIC_DIR" in os.environ and os.path.isdir(os.environ["HERDR_STATIC_DIR"]):
        return os.environ["HERDR_STATIC_DIR"]

    candidates = [
        # In repo: src/bridge/adapters/http/../../../../web/dist -> repo/web/dist
        os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../web/dist")),
        # In ~/.config/herdr-telegram: bridge/adapters/http/../../../web/dist -> ~/.config/herdr-telegram/web/dist
        os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../web/dist")),
        "/home/sm/proyectos/herdr-telegram-bridge/web/dist",
    ]
    for c in candidates:
        if os.path.isdir(c):
            return c
    return candidates[0]


class HttpApiServer:
    """Runs the ThreadingHTTPServer in a background daemon thread."""

    def __init__(
        self,
        service: AgentBridgeService,
        topic_repo: StateRepositoryPort,
        host: str = "127.0.0.1",
        port: int = 8765,
        static_dir: Optional[str] = None,
    ):
        self.service = service
        self.topic_repo = topic_repo
        self.host = host
        self.port = port
        self.static_dir = _resolve_static_dir(static_dir)

        class CustomHandler(MiniAppHandler):
            pass

        CustomHandler.server_service = self.service
        CustomHandler.server_topic_repo = self.topic_repo
        CustomHandler.static_dir = self.static_dir

        self.server = ThreadingHTTPServer((self.host, self.port), CustomHandler)
        self._thread: Optional[threading.Thread] = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self.server.serve_forever, name="HttpApiServerThread", daemon=True
        )
        self._thread.start()
        logger.info("HTTP API server started on http://%s:%d", self.host, self.port)

    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            logger.info("HTTP API server stopped.")
