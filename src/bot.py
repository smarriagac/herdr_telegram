#!/usr/bin/env python3
"""
Herdr Telegram Bridge
Bridge between Telegram and Herdr AI agent workspace manager with Telegram Forum Topic isolation.
"""

import html
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request


def resolve_paths():
    """Resolves config.json and topics.json paths with sensible fallbacks."""
    env_cfg = os.environ.get("HERDR_TELEGRAM_CONFIG")
    if env_cfg and os.path.exists(env_cfg):
        cfg_dir = os.path.dirname(os.path.abspath(env_cfg))
        return os.path.abspath(env_cfg), os.path.join(cfg_dir, "topics.json")

    local_cfg = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    if os.path.exists(local_cfg):
        return local_cfg, os.path.join(os.path.dirname(local_cfg), "topics.json")

    root_cfg = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json"
    )
    if os.path.exists(root_cfg):
        return root_cfg, os.path.join(os.path.dirname(root_cfg), "topics.json")

    user_cfg_dir = os.path.expanduser("~/.config/herdr-telegram")
    return os.path.join(user_cfg_dir, "config.json"), os.path.join(
        user_cfg_dir, "topics.json"
    )


CONFIG_PATH, TOPICS_PATH = resolve_paths()

if not os.path.exists(CONFIG_PATH):
    print(f"Error: Config file not found at {CONFIG_PATH}", file=sys.stderr)
    print(
        "Please copy config.example.json to config.json and configure your tokens.",
        file=sys.stderr,
    )
    sys.exit(1)

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    config = json.load(f)

BOT_TOKEN = config["bot_token"]
ALLOWED_CHAT_ID = int(config["allowed_chat_id"])
GROUP_CHAT_ID = config.get("group_chat_id")
HERDR_BIN = os.path.expanduser(config.get("herdr_bin", "herdr"))
PROJECTS_DIR = os.path.expanduser(config.get("projects_dir", "~/proyectos"))
API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"

STATUS_CONFIG = {
    "idle": {"icon": "💤", "label": "Libre (esperando tareas)"},
    "working": {"icon": "⏳", "label": "Laburando en segundo plano"},
    "blocked": {"icon": "⚠️", "label": "Esperando tu confirmación"},
    "done": {"icon": "✅", "label": "Tarea completada"},
    "unknown": {"icon": "❓", "label": "Desconocido"},
}

KEY_ALIASES = {
    "yes": ["y", "enter"],
    "si": ["y", "enter"],
    "no": ["n", "enter"],
    "ok": ["enter"],
}

PERSISTENT_KEYBOARD = {
    "keyboard": [
        [{"text": "🤖 Mis Agentes"}, {"text": "➕ Nuevo Agente"}],
        [{"text": "📄 Ver Salida"}, {"text": "❓ Ayuda / Comandos"}],
    ],
    "resize_keyboard": True,
    "is_persistent": True,
}

topics_lock = threading.Lock()


def load_topics():
    with topics_lock:
        if not os.path.exists(TOPICS_PATH):
            return {}
        try:
            with open(TOPICS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading topics.json: {e}", file=sys.stderr)
            return {}


def save_topics(topics):
    with topics_lock:
        try:
            os.makedirs(os.path.dirname(os.path.abspath(TOPICS_PATH)), exist_ok=True)
            with open(TOPICS_PATH, "w", encoding="utf-8") as f:
                json.dump(topics, f, indent=2)
        except Exception as e:
            print(f"Error saving topics.json: {e}", file=sys.stderr)


def call_telegram_api(method, payload):
    url = f"{API_BASE}/{method}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode() if e.fp else str(e)
        if "message is not modified" in err_msg.lower():
            return {"ok": True, "result": "not_modified"}
        print(f"Error calling {method}: HTTP {e.code} - {err_msg}", file=sys.stderr)
        if method in ("sendMessage", "editMessageText") and "parse_mode" in payload:
            payload_fallback = dict(payload)
            payload_fallback.pop("parse_mode", None)
            return call_telegram_api(method, payload_fallback)
        return None
    except Exception as e:
        print(f"Error calling {method}: {e}", file=sys.stderr)
        return None


def send_message(
    chat_id, text, reply_markup=None, parse_mode="HTML", message_thread_id=None
):
    if len(text) > 4000:
        text = text[:3950] + "\n... [Texto truncado por límite de Telegram]"

    payload = {"chat_id": chat_id, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup:
        payload["reply_markup"] = reply_markup
    if message_thread_id:
        payload["message_thread_id"] = message_thread_id

    return call_telegram_api("sendMessage", payload)


def edit_message_text(
    chat_id, message_id, text, reply_markup=None, parse_mode="HTML"
):
    if len(text) > 4000:
        text = text[:3950] + "\n... [Texto truncado por límite de Telegram]"

    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup:
        payload["reply_markup"] = reply_markup

    return call_telegram_api("editMessageText", payload)


def answer_callback(callback_query_id, text=None):
    payload = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
        payload["show_alert"] = False
    return call_telegram_api("answerCallbackQuery", payload)


def ensure_topic_for_workspace(ws_label):
    if not GROUP_CHAT_ID:
        return None

    clean_label = ws_label.strip()
    topics = load_topics()
    if clean_label in topics:
        return topics[clean_label]

    topic_name = f"📁 {clean_label}"
    res = call_telegram_api(
        "createForumTopic",
        {
            "chat_id": GROUP_CHAT_ID,
            "name": topic_name,
        },
    )
    if res and res.get("ok"):
        thread_id = res["result"]["message_thread_id"]
        topics[clean_label] = thread_id
        save_topics(topics)

        kb = [
            [
                {
                    "text": "📄 Ver Terminal",
                    "callback_data": f"act|read|{clean_label}",
                },
                {
                    "text": "🔄 Estado",
                    "callback_data": f"act|topicstatus|{clean_label}",
                },
            ],
            [
                {
                    "text": "✅ Aceptar (Enter)",
                    "callback_data": f"act|enter|{clean_label}",
                },
                {"text": "👍 Sí", "callback_data": f"act|yes|{clean_label}"},
                {
                    "text": "❌ Cancelar",
                    "callback_data": f"act|esc|{clean_label}",
                },
            ],
        ]
        send_message(
            GROUP_CHAT_ID,
            f"🚀 <b>Espacio de trabajo dedicado para {clean_label}</b>\n\n"
            f"• Las alertas y decisiones de este agente quedarán <b>exclusivamente en este tema</b>.\n"
            f"• <b>Para darle una orden:</b> simplemente escribí tu mensaje acá y se enviará al agente.",
            reply_markup={"inline_keyboard": kb},
            message_thread_id=thread_id,
        )
        return thread_id

    return None


def close_topic_for_workspace(ws_label):
    if not GROUP_CHAT_ID:
        return
    clean_label = ws_label.strip()
    topics = load_topics()
    if clean_label in topics:
        thread_id = topics[clean_label]
        call_telegram_api(
            "closeForumTopic",
            {
                "chat_id": GROUP_CHAT_ID,
                "message_thread_id": thread_id,
            },
        )
        del topics[clean_label]
        save_topics(topics)


def parse_callback_data(data):
    if not data:
        return None, None

    if data.startswith("act|") or data.startswith("act:"):
        body = data[4:]
    else:
        return None, None

    if "|" in body:
        parts = body.split("|", 1)
        action = parts[0]
        target = parts[1] if len(parts) > 1 and parts[1] else None
        if action and ":" in action and target is None:
            action, target = action.split(":", 1)
    elif ":" in body:
        parts = body.split(":", 1)
        action = parts[0]
        target = parts[1] if len(parts) > 1 and parts[1] else None
    else:
        action = body
        target = None

    return action, target


def setup_bot_commands():
    commands = [
        {"command": "status", "description": "Panel visual de agentes"},
        {"command": "new", "description": "Crear nuevo agente (/new <nombre>)"},
        {"command": "read", "description": "Ver terminal del agente"},
        {
            "command": "enter",
            "description": "Aceptar opción en agente bloqueado",
        },
        {"command": "yes", "description": "Responder Sí (y + Enter)"},
        {"command": "esc", "description": "Cancelar / Escape"},
        {"command": "rename", "description": "Ponerle nombre a un agente"},
        {"command": "close", "description": "Cerrar un proyecto o agente"},
        {"command": "help", "description": "Ver ayuda completa"},
    ]
    return call_telegram_api("setMyCommands", {"commands": commands})


def run_herdr_cmd(args, timeout=25):
    cmd = [HERDR_BIN] + args
    try:
        res = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
        )
        return res.returncode, res.stdout.strip(), res.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "Timeout ejecutando comando de Herdr"
    except Exception as e:
        return -1, "", str(e)


def get_agent_list_with_metadata():
    code, out, err = run_herdr_cmd(["agent", "list"])
    if code != 0 or not out:
        return None, err or "Error al listar agentes"
    try:
        agents = json.loads(out).get("result", {}).get("agents", [])
    except Exception as e:
        return None, f"JSON parse error: {e}"

    ws_map = {}
    tab_map = {}

    code_ws, out_ws, _ = run_herdr_cmd(["workspace", "list"])
    if code_ws == 0 and out_ws:
        try:
            for w in json.loads(out_ws).get("result", {}).get("workspaces", []):
                ws_map[w.get("workspace_id")] = w.get("label")
        except Exception:
            pass

    code_tab, out_tab, _ = run_herdr_cmd(["tab", "list"])
    if code_tab == 0 and out_tab:
        try:
            for t in json.loads(out_tab).get("result", {}).get("tabs", []):
                tab_map[t.get("tab_id")] = t.get("label")
        except Exception:
            pass

    for ag in agents:
        ws_id = ag.get("workspace_id")
        tab_id = ag.get("tab_id")
        ag["workspace_label"] = ws_map.get(ws_id, ws_id)
        ag["tab_label"] = tab_map.get(tab_id, "")

        parts = []
        if ag["workspace_label"]:
            parts.append(ag["workspace_label"])
        if ag["tab_label"] and ag["tab_label"] != "1":
            parts.append(ag["tab_label"])
        if ag.get("name"):
            parts.append(f"<b>{ag['name']}</b>")

        ag["display_name"] = " · ".join(parts) if parts else ag.get("pane_id")

    return agents, None


def resolve_target(agents, target_arg=None, prefer_blocked=True):
    if target_arg:
        target_arg = target_arg.strip()
        if agents:
            for ag in agents:
                if ag.get("pane_id") == target_arg:
                    return ag.get("pane_id")
            for ag in agents:
                name = (ag.get("name") or "").lower()
                ws = (ag.get("workspace_label") or "").lower()
                if target_arg.lower() in (name, ws):
                    return ag.get("pane_id")
            for ag in agents:
                pid = ag.get("pane_id", "")
                if pid.startswith(target_arg + ":") or pid.startswith(
                    target_arg
                ):
                    return pid
            if target_arg.isdigit():
                for ag in agents:
                    pid = ag.get("pane_id", "")
                    if f"w{target_arg}:" in pid:
                        return pid
        return target_arg

    if not agents:
        return None

    if prefer_blocked:
        for ag in agents:
            if ag.get("agent_status") == "blocked":
                return ag.get("pane_id")
    for ag in agents:
        if ag.get("focused"):
            return ag.get("pane_id")
    return agents[0].get("pane_id")


def get_display_for_target(agents, target):
    if agents and target:
        for ag in agents:
            if (
                ag.get("pane_id") == target
                or ag.get("workspace_label") == target
            ):
                return ag.get("display_name", target)
    return target


def build_status_reply():
    agents, err = get_agent_list_with_metadata()
    if err:
        return f"❌ Error conectando con Herdr: {html.escape(err)}", None

    if not agents:
        markup = {
            "inline_keyboard": [
                [
                    {
                        "text": "➕ Crear mi primer agente",
                        "callback_data": "act|asknew",
                    }
                ],
                {"text": "🔄 Actualizar", "callback_data": "act|refresh"},
            ]
        }
        return (
            "╭────────────────────────────╮\n"
            "│   🚀 <b>PANEL DE CONTROL HERDR</b>\n"
            "╰────────────────────────────╯\n\n"
            "<i>No hay agentes activos en Herdr en este momento.</i>\n\n"
            "Tocá el botón abajo para crear tu primer proyecto.",
            markup,
        )

    lines = [
        "╭────────────────────────────╮\n"
        "│   🚀 <b>PANEL DE CONTROL HERDR</b>\n"
        "╰────────────────────────────╯\n"
    ]
    inline_keyboard = []

    for ag in agents:
        pid = ag.get("pane_id", "?")
        agent_type = ag.get("agent", "agent")
        display_name = ag.get("display_name", pid)
        st = ag.get("agent_status", "unknown")
        status_info = STATUS_CONFIG.get(st, STATUS_CONFIG["unknown"])
        focused = " 🎯 [Activo]" if ag.get("focused") else ""

        ws_label = ag.get("workspace_label") or pid
        btn_label = ag.get("name") or ws_label

        lines.append(f"╭─ 📁 <b>{display_name}</b>{focused}")
        lines.append(
            f"│  🆔 Panel: <code>{pid}</code> · Motor: <code>{agent_type}</code>"
        )
        lines.append(f"│  {status_info['icon']} <b>{status_info['label']}</b>")
        lines.append("╰──────────────────────────\n")

        if st == "blocked":
            inline_keyboard.append([
                {
                    "text": f"✅ Aceptar ({btn_label})",
                    "callback_data": f"act|enter|{pid}",
                },
                {"text": "👍 Sí", "callback_data": f"act|yes|{pid}"},
                {"text": "❌ Cancelar", "callback_data": f"act|esc|{pid}"},
            ])

        inline_keyboard.append([
            {
                "text": f"📄 Salida [{btn_label}]",
                "callback_data": f"act|read|{pid}",
            },
            {"text": "💬 Dar orden", "callback_data": f"act|askprompt|{pid}"},
        ])

    inline_keyboard.append([
        {"text": "➕ Nuevo Agente", "callback_data": "act|asknew"},
        {"text": "🔄 Actualizar Panel", "callback_data": "act|refresh"},
    ])

    return "".join(lines), {"inline_keyboard": inline_keyboard}


def handle_new(args):
    if not args:
        markup = {
            "force_reply": True,
            "input_field_placeholder": "nombre-del-proyecto",
            "selective": True,
        }
        msg = (
            "╭─ ➕ <b>Crear Nuevo Proyecto</b>\n"
            "│\n"
            "│  <b>Respondé directamente a este mensaje</b>\n"
            "│  con el nombre de tu proyecto (ej: <code>tienda</code>)\n"
            "│\n"
            "│  O escribí el comando:\n"
            "│  <code>/new &lt;nombre&gt; [motor]</code>\n"
            "╰──────────────────────────\n"
            "<i>Motores disponibles: agy (default), claude, codex, opencode</i>"
        )
        return msg, markup

    name = args[0].strip()
    clean_name = "".join(
        c for c in name if c.isalnum() or c in ("-", "_")
    ).lower()
    if not clean_name:
        return "❌ Nombre inválido. Usá solo letras, números o guiones.", None

    kind = args[1].lower() if len(args) > 1 else "agy"
    proj_path = os.path.join(PROJECTS_DIR, clean_name)
    try:
        os.makedirs(proj_path, exist_ok=True)
    except Exception as e:
        return f"❌ Error creando carpeta en disco: {html.escape(str(e))}", None

    code, out, err = run_herdr_cmd(
        ["workspace", "create", "--label", clean_name, "--cwd", proj_path]
    )
    if code != 0 or not out:
        return (
            f"❌ Error creando workspace en Herdr: {html.escape(err or out)}",
            None,
        )

    try:
        data = json.loads(out)
        pane_id = data["result"]["root_pane"]["pane_id"]
        ws_id = data["result"]["workspace"]["workspace_id"]
    except Exception as e:
        return (
            f"❌ Error procesando respuesta de Herdr: {html.escape(str(e))}",
            None,
        )

    code_ag, out_ag, err_ag = run_herdr_cmd(
        [
            "agent",
            "start",
            clean_name,
            "--kind",
            kind,
            "--pane",
            pane_id,
        ],
        timeout=35,
    )
    if code_ag != 0:
        run_herdr_cmd(["workspace", "close", ws_id])
        return (
            f"❌ Error iniciando agente ({kind}): {html.escape(err_ag or out_ag)}",
            None,
        )

    ensure_topic_for_workspace(clean_name)

    markup = {
        "inline_keyboard": [
            [
                {
                    "text": f"📄 Ver Terminal [{clean_name}]",
                    "callback_data": f"act|read|{pane_id}",
                }
            ],
            [{"text": "📋 Ver Panel Principal", "callback_data": "act|refresh"}],
        ]
    }
    msg = (
        "╭─ 🎉 <b>¡Agente creado exitosamente!</b>\n"
        f"│  📁 Proyecto: <b>{clean_name}</b>\n"
        f"│  🆔 Panel: <code>{pane_id}</code>\n"
        f"│  ⚙️ Motor: <code>{kind}</code>\n"
        f"│  📂 Ruta: <code>{proj_path}</code>\n"
        "╰──────────────────────────\n\n"
        f"💡 <i>Se creó el tema <b>#📁 {clean_name}</b> en el grupo. Podés escribirle directamente ahí.</i>"
    )
    return msg, markup


def handle_close(args):
    if not args:
        return (
            "Uso: /close <nombre_o_id>\nEjemplo: /close deportivo",
            None,
        )

    agents, _ = get_agent_list_with_metadata()
    target_arg = args[0]
    target_pane = resolve_target(agents, target_arg, prefer_blocked=False)

    ws_id = None
    ws_label = None
    display = target_arg
    if agents:
        for ag in agents:
            if ag.get("pane_id") == target_pane:
                ws_id = ag.get("workspace_id")
                ws_label = ag.get("workspace_label")
                display = ag.get("display_name", target_pane)
                break

    if not ws_id:
        if target_arg.startswith("w") and ":" not in target_arg:
            ws_id = target_arg
        else:
            return (
                f"❌ No se encontró ningún proyecto llamado '{target_arg}'.",
                None,
            )

    code, out, err = run_herdr_cmd(["workspace", "close", ws_id])
    if code != 0:
        return (
            f"❌ Error cerrando workspace {ws_id}: {html.escape(err or out)}",
            None,
        )

    if ws_label:
        close_topic_for_workspace(ws_label)

    return (
        f"🗑️ Proyecto <b>{html.escape(display)}</b> cerrado y archivado"
        " correctamente.",
        None,
    )


def handle_read(args):
    agents, _ = get_agent_list_with_metadata()
    target_arg = None
    num_lines = "25"

    if args:
        if len(args) == 1 and args[0].isdigit():
            num_lines = args[0]
            target_arg = None
        else:
            target_arg = args[0]
            if len(args) > 1 and args[1].isdigit():
                num_lines = args[1]

    target = resolve_target(agents, target_arg, prefer_blocked=True)
    if not target:
        return (
            "Uso: /read <pane_id> [líneas]\nEjemplo: /read deportivo 25",
            None,
        )

    target_name = get_display_for_target(agents, target)

    code, out, err = run_herdr_cmd(
        ["agent", "read", target, "--lines", num_lines, "--format", "text"]
    )
    if code != 0:
        return (
            f"❌ Error leyendo {target}:"
            f" {html.escape(err or 'Fallo desconocido')}",
            None,
        )

    clean_out = html.escape(out.strip() or "(Sin salida reciente)")

    switcher_row = []
    if agents and len(agents) > 1:
        for ag in agents:
            ag_pid = ag.get("pane_id")
            ag_label = ag.get("name") or ag.get("workspace_label") or ag_pid
            is_cur = ag_pid == target
            btn_txt = f"📍 {ag_label}" if is_cur else f"📁 {ag_label}"
            switcher_row.append(
                {"text": btn_txt, "callback_data": f"act|read|{ag_pid}"}
            )

    is_blocked = False
    if agents:
        for ag in agents:
            if (
                ag.get("pane_id") == target
                and ag.get("agent_status") == "blocked"
            ):
                is_blocked = True
                break

    inline_kb = []
    if switcher_row:
        for i in range(0, len(switcher_row), 2):
            inline_kb.append(switcher_row[i : i + 2])

    if is_blocked:
        inline_kb.append([
            {
                "text": "✅ Aceptar (Enter)",
                "callback_data": f"act|enter|{target}",
            },
            {"text": "👍 Sí", "callback_data": f"act|yes|{target}"},
            {"text": "❌ Cancelar", "callback_data": f"act|esc|{target}"},
        ])
    else:
        inline_kb.append([
            {"text": "💬 Dar orden", "callback_data": f"act|askprompt|{target}"},
        ])

    inline_kb.append([
        {
            "text": "🔄 Recargar salida",
            "callback_data": f"act|read_reload|{target}",
        },
        {"text": "📋 Panel Principal", "callback_data": "act|refresh"},
    ])

    return (
        f"╭─ 📄 <b>Terminal: {target_name}</b>"
        f" (<code>{target}</code>)\n╰──────────────────────────\n<pre>{clean_out}</pre>",
        {"inline_keyboard": inline_kb},
    )


def handle_prompt(args):
    agents, _ = get_agent_list_with_metadata()

    if not args:
        return (
            "Uso: /prompt <nombre_o_id> <mensaje>\nEjemplo: /prompt deportivo"
            " Crea el modelo de usuario"
        )

    target_candidate = args[0]
    matched = resolve_target(agents, target_candidate, prefer_blocked=False)

    if matched and (
        ":" in target_candidate
        or target_candidate.startswith("w")
        or any(
            ag.get("workspace_label") == target_candidate.lower()
            for ag in (agents or [])
        )
    ):
        target = matched
        prompt_text = " ".join(args[1:])
    else:
        target = resolve_target(agents, prefer_blocked=False)
        prompt_text = " ".join(args)

    if not prompt_text:
        return "Uso: /prompt <nombre_o_id> <mensaje>"

    code, out, err = run_herdr_cmd(["agent", "prompt", target, prompt_text])
    if code != 0:
        clean_err = html.escape(err or out)
        if "agent_blocked" in clean_err:
            return (
                f"⚠️ El agente <code>{target}</code> está <b>bloqueado</b>"
                " esperando confirmación.\nTocá los botones táctiles o usá"
                f" <code>/enter {target}</code> para continuar."
            )
        return f"❌ Error enviando prompt a {target}: {clean_err}"

    target_name = get_display_for_target(agents, target)
    return (
        f"🚀 <b>Orden enviada a {target_name}:</b>\n<i>«{html.escape(prompt_text)}»</i>"
    )


def handle_rename(args):
    if len(args) < 2:
        return (
            "Uso: /rename <nombre_o_id> <nuevo_nombre>\nEjemplo: /rename"
            " deportivo api-backend"
        )

    agents, _ = get_agent_list_with_metadata()
    target = resolve_target(agents, args[0], prefer_blocked=False)
    new_name = args[1]

    cmd = ["agent", "rename", target]
    if new_name == "--clear":
        cmd.append("--clear")
    else:
        cmd.append(new_name)

    code, out, err = run_herdr_cmd(cmd)
    if code != 0:
        return f"❌ Error renombrando {target}: {html.escape(err or out)}"

    if new_name == "--clear":
        return f"✅ Nombre personalizado eliminado de <code>{target}</code>."
    return (
        f"✅ Agente <code>{target}</code> renombrado a"
        f" <b>{html.escape(new_name)}</b>."
    )


def handle_quick_key(key_list, args):
    agents, _ = get_agent_list_with_metadata()
    target_arg = args[0] if args else None
    target = resolve_target(agents, target_arg, prefer_blocked=True)
    if not target:
        return "No hay ningún agente activo disponible."

    code, out, err = run_herdr_cmd(["agent", "send-keys", target] + key_list)
    if code != 0:
        return (
            f"❌ Error enviando {' '.join(key_list)} a {target}:"
            f" {html.escape(err or out)}"
        )

    target_name = get_display_for_target(agents, target)
    return f"✅ Enviado <code>{' '.join(key_list)}</code> a <b>{target_name}</b>."


def handle_help():
    return (
        "╭────────────────────────────╮\n"
        "│   📖 <b>GUÍA DE COMANDOS HERDR</b>\n"
        "╰────────────────────────────╯\n\n"
        "<b>En los Temas dedicados por agente:</b>\n"
        "• Cada proyecto tiene su propio canal (#deportivo, #prueba, etc.).\n"
        "• <b>Simplemente escribí tu mensaje en el tema</b> y se enviará como"
        " orden a ese agente.\n"
        "• Las alertas y preguntas de confirmación van a su tema respectivo sin"
        " mezclarse.\n\n"
        "<b>En el tema General o Chat Privado:</b>\n"
        "• <code>/status</code>: Ver panel de control general.\n"
        "• <code>/new &lt;nombre&gt; [motor]</code>: Crear nuevo proyecto y su"
        " tema.\n"
        "• <code>/read &lt;proyecto&gt;</code>: Ver la terminal de un"
        " agente.\n"
        "• <code>/close &lt;proyecto&gt;</code>: Cerrar el proyecto y archivar"
        " su tema."
    )


def handle_callback_query(cq):
    from_id = cq.get("from", {}).get("id")
    msg = cq.get("message", {})
    chat_id = msg.get("chat", {}).get("id")
    thread_id = msg.get("message_thread_id")
    msg_id = msg.get("message_id")
    cq_id = cq.get("id")
    data = cq.get("data", "")

    if chat_id != ALLOWED_CHAT_ID and chat_id != GROUP_CHAT_ID:
        return
    if from_id not in (ALLOWED_CHAT_ID, 1087968824):
        return

    action, raw_target = parse_callback_data(data)
    if not action:
        answer_callback(cq_id)
        return

    agents, _ = get_agent_list_with_metadata()
    target = resolve_target(agents, raw_target, prefer_blocked=True)

    if action == "refresh":
        answer_callback(cq_id, "Actualizando...")
        text, markup = build_status_reply()
        if msg_id:
            res = edit_message_text(chat_id, msg_id, text, reply_markup=markup)
            if res and res.get("result") == "not_modified":
                answer_callback(cq_id, "✅ Panel al día (sin cambios)")
        else:
            send_message(
                chat_id, text, reply_markup=markup, message_thread_id=thread_id
            )

    elif action == "asknew":
        answer_callback(cq_id)
        text, markup = handle_new([])
        send_message(
            chat_id, text, reply_markup=markup, message_thread_id=thread_id
        )

    elif action == "askprompt" and target:
        answer_callback(cq_id)
        display_name = get_display_for_target(agents, target)
        markup = {
            "force_reply": True,
            "input_field_placeholder": f"Orden para {display_name}...",
            "selective": True,
        }
        send_message(
            chat_id,
            f"💬 <b>Nueva orden para {display_name}:</b>\n\n"
            "Respondé directamente a este mensaje con la tarea o instrucción"
            " que debe realizar el agente:",
            reply_markup=markup,
            message_thread_id=thread_id,
        )

    elif action == "enter" and target:
        code, _, err = run_herdr_cmd(["agent", "send-keys", target, "enter"])
        display_name = get_display_for_target(agents, target)
        if code == 0:
            answer_callback(cq_id, f"✅ Enter enviado a {display_name}")
            send_message(
                chat_id,
                f"✅ <b>Enter</b> enviado a <b>{display_name}</b>.",
                message_thread_id=thread_id,
            )
        else:
            answer_callback(cq_id, "Error al enviar Enter")
            send_message(
                chat_id,
                f"❌ Error enviando Enter: {html.escape(err)}",
                message_thread_id=thread_id,
            )

    elif action == "yes" and target:
        code, _, err = run_herdr_cmd(
            ["agent", "send-keys", target, "y", "enter"]
        )
        display_name = get_display_for_target(agents, target)
        if code == 0:
            answer_callback(cq_id, f"👍 Sí enviado a {display_name}")
            send_message(
                chat_id,
                f"👍 <b>'y' + Enter</b> enviado a <b>{display_name}</b>.",
                message_thread_id=thread_id,
            )
        else:
            answer_callback(cq_id, "Error al enviar Sí")
            send_message(
                chat_id,
                f"❌ Error enviando Sí: {html.escape(err)}",
                message_thread_id=thread_id,
            )

    elif action == "esc" and target:
        code, _, err = run_herdr_cmd(["agent", "send-keys", target, "esc"])
        display_name = get_display_for_target(agents, target)
        if code == 0:
            answer_callback(cq_id, f"❌ Escape enviado a {display_name}")
            send_message(
                chat_id,
                f"❌ <b>Escape</b> enviado a <b>{display_name}</b>.",
                message_thread_id=thread_id,
            )
        else:
            answer_callback(cq_id, "Error al enviar Escape")
            send_message(
                chat_id,
                f"❌ Error enviando Escape: {html.escape(err)}",
                message_thread_id=thread_id,
            )

    elif action in ("read", "read_reload") and target:
        answer_callback(cq_id, "Cargando salida...")
        text, markup = handle_read([target, "25"])
        if action == "read_reload" and msg_id:
            res = edit_message_text(chat_id, msg_id, text, reply_markup=markup)
            if res and res.get("result") == "not_modified":
                answer_callback(cq_id, "✅ Salida al día")
        else:
            send_message(
                chat_id, text, reply_markup=markup, message_thread_id=thread_id
            )

    elif action == "topicstatus" and target:
        answer_callback(cq_id, "Cargando estado...")
        text, markup = handle_read([target, "15"])
        send_message(
            chat_id, text, reply_markup=markup, message_thread_id=thread_id
        )

    else:
        answer_callback(cq_id)


def process_message(msg):
    chat = msg.get("chat", {})
    chat_id = chat.get("id")
    from_user = msg.get("from", {})
    from_id = from_user.get("id")
    thread_id = msg.get("message_thread_id")
    text = msg.get("text", "").strip()

    if chat_id != ALLOWED_CHAT_ID and chat_id != GROUP_CHAT_ID:
        return
    if from_id not in (ALLOWED_CHAT_ID, 1087968824):
        return

    if not text:
        return

    topics = load_topics()

    matched_workspace = None
    if chat_id == GROUP_CHAT_ID and thread_id:
        for ws, t_id in topics.items():
            if t_id == thread_id:
                matched_workspace = ws
                break

    # 1. ForceReply
    reply_to = msg.get("reply_to_message", {})
    if reply_to:
        reply_orig_text = reply_to.get("text", "")
        if (
            "Crear Nuevo Proyecto" in reply_orig_text
            or "nombre de tu proyecto" in reply_orig_text
        ):
            text_resp, markup = handle_new([text])
            send_message(
                chat_id,
                text_resp,
                reply_markup=markup,
                message_thread_id=thread_id,
            )
            return

        if "Nueva orden para" in reply_orig_text:
            m = re.search(r"Nueva orden para\s+([^:\n]+):", reply_orig_text)
            if m:
                target_cand = m.group(1).strip()
                res = handle_prompt([target_cand, text])
                send_message(chat_id, res, message_thread_id=thread_id)
                return

    # 2. Plain text inside a specific project topic is a direct prompt
    if matched_workspace and not text.startswith("/"):
        res = handle_prompt([matched_workspace, text])
        send_message(chat_id, res, message_thread_id=thread_id)
        return

    # 3. Persistent keyboard commands
    clean_lower = text.lower()
    if clean_lower in ("🤖 mis agentes", "mis agentes"):
        text_resp, markup = build_status_reply()
        send_message(
            chat_id, text_resp, reply_markup=markup, message_thread_id=thread_id
        )
        return
    elif clean_lower in ("➕ nuevo agente", "nuevo agente"):
        text_resp, markup = handle_new([])
        send_message(
            chat_id, text_resp, reply_markup=markup, message_thread_id=thread_id
        )
        return
    elif clean_lower in ("📄 ver salida", "ver salida"):
        arg = [matched_workspace] if matched_workspace else []
        text_resp, markup = handle_read(arg)
        send_message(
            chat_id, text_resp, reply_markup=markup, message_thread_id=thread_id
        )
        return
    elif clean_lower in ("❓ ayuda / comandos", "ayuda"):
        send_message(
            chat_id,
            handle_help(),
            reply_markup=PERSISTENT_KEYBOARD,
            message_thread_id=thread_id,
        )
        return

    # 4. Slash commands
    parts = text.split()
    cmd = parts[0].lower()
    if "@" in cmd:
        cmd = cmd.split("@")[0]
    args = parts[1:]

    if matched_workspace and not args:
        if cmd in ("/read", "/enter", "/yes", "/esc", "/close"):
            args = [matched_workspace]

    if cmd == "/start":
        welcome = (
            "🚀 <b>¡Bienvenido a Herdr Mission Control!</b>\n\n"
            "Los agentes se sincronizan en temas aislados para que no se"
            " mezclen tus proyectos."
        )
        send_message(
            chat_id,
            welcome,
            reply_markup=PERSISTENT_KEYBOARD,
            message_thread_id=thread_id,
        )
        text_resp, markup = build_status_reply()
        send_message(
            chat_id, text_resp, reply_markup=markup, message_thread_id=thread_id
        )
    elif cmd in ("/agents", "/status"):
        text_resp, markup = build_status_reply()
        send_message(
            chat_id, text_resp, reply_markup=markup, message_thread_id=thread_id
        )
    elif cmd == "/new":
        text_resp, markup = handle_new(args)
        send_message(
            chat_id, text_resp, reply_markup=markup, message_thread_id=thread_id
        )
    elif cmd == "/close":
        text_resp, markup = handle_close(args)
        send_message(
            chat_id, text_resp, reply_markup=markup, message_thread_id=thread_id
        )
    elif cmd == "/read":
        text_resp, markup = handle_read(args)
        send_message(
            chat_id, text_resp, reply_markup=markup, message_thread_id=thread_id
        )
    elif cmd == "/prompt":
        send_message(chat_id, handle_prompt(args), message_thread_id=thread_id)
    elif cmd == "/rename":
        send_message(chat_id, handle_rename(args), message_thread_id=thread_id)
    elif cmd in ("/enter", "/ok"):
        send_message(
            chat_id,
            handle_quick_key(["enter"], args),
            message_thread_id=thread_id,
        )
    elif cmd in ("/y", "/yes", "/si"):
        send_message(
            chat_id,
            handle_quick_key(["y", "enter"], args),
            message_thread_id=thread_id,
        )
    elif cmd in ("/n", "/no"):
        send_message(
            chat_id,
            handle_quick_key(["n", "enter"], args),
            message_thread_id=thread_id,
        )
    elif cmd in ("/esc", "/cancel"):
        send_message(
            chat_id,
            handle_quick_key(["esc"], args),
            message_thread_id=thread_id,
        )
    elif cmd == "/help":
        send_message(
            chat_id,
            handle_help(),
            reply_markup=PERSISTENT_KEYBOARD,
            message_thread_id=thread_id,
        )
    else:
        send_message(
            chat_id,
            "💡 Mandá /help para ver la lista de comandos o tocá los botones"
            " inferiores.",
            reply_markup=PERSISTENT_KEYBOARD,
            message_thread_id=thread_id,
        )


def state_watcher_thread():
    """Monitors agents and sends alerts exclusively to each project's topic."""
    known_states = {}
    time.sleep(3)

    while True:
        try:
            agents, err = get_agent_list_with_metadata()
            if agents is not None:
                current_pids = set()
                for ag in agents:
                    pid = ag.get("pane_id")
                    st = ag.get("agent_status")
                    ws_label = ag.get("workspace_label") or pid
                    current_pids.add(pid)

                    thread_id = (
                        ensure_topic_for_workspace(ws_label)
                        if GROUP_CHAT_ID
                        else None
                    )
                    target_chat = (
                        GROUP_CHAT_ID if GROUP_CHAT_ID else ALLOWED_CHAT_ID
                    )

                    if pid in known_states:
                        old_st = known_states[pid]
                        if old_st != st:
                            new_info = STATUS_CONFIG.get(
                                st, STATUS_CONFIG["unknown"]
                            )
                            old_info = STATUS_CONFIG.get(
                                old_st, STATUS_CONFIG["unknown"]
                            )
                            display_name = ag.get("display_name", pid)
                            btn_label = ag.get("name") or ws_label

                            msg = (
                                "╭─ 🔔 <b>Actualización de Estado</b>\n"
                                f"│  📁 Proyecto: <b>{display_name}</b>\n"
                                f"│  Transición: {old_info['icon']} ➔"
                                f" <b>{new_info['icon']}"
                                f" {new_info['label']}</b>\n"
                                "╰──────────────────────────"
                            )
                            markup = None

                            if st == "blocked":
                                code, out, _ = run_herdr_cmd([
                                    "agent",
                                    "read",
                                    pid,
                                    "--lines",
                                    "10",
                                    "--format",
                                    "text",
                                ])
                                if code == 0 and out.strip():
                                    clean_out = html.escape(out.strip())
                                    msg += (
                                        "\n\n❓ <b>Esperando respuesta:</b>\n<pre>"
                                        f"{clean_out}</pre>"
                                    )

                                markup = {
                                    "inline_keyboard": [
                                        [
                                            {
                                                "text": (
                                                    f"✅ Aceptar ({btn_label})"
                                                ),
                                                "callback_data": (
                                                    f"act|enter|{pid}"
                                                ),
                                            },
                                            {
                                                "text": "👍 Sí",
                                                "callback_data": (
                                                    f"act|yes|{pid}"
                                                ),
                                            },
                                            {
                                                "text": "❌ Cancelar",
                                                "callback_data": (
                                                    f"act|esc|{pid}"
                                                ),
                                            },
                                        ],
                                        [
                                            {
                                                "text": "📄 Ver más líneas",
                                                "callback_data": (
                                                    f"act|read|{pid}"
                                                ),
                                            },
                                            {
                                                "text": "📋 Panel Principal",
                                                "callback_data": "act|refresh",
                                            },
                                        ],
                                    ]
                                }
                            elif st in ("idle", "done") and old_st == "working":
                                msg += (
                                    "\n\n🎉 <i>¡El agente completó la tarea"
                                    " asignada!</i>"
                                )
                                markup = {
                                    "inline_keyboard": [
                                        [
                                            {
                                                "text": (
                                                    "📄 Ver resultado"
                                                    f" [{btn_label}]"
                                                ),
                                                "callback_data": (
                                                    f"act|read|{pid}"
                                                ),
                                            }
                                        ],
                                        [
                                            {
                                                "text": "📋 Panel",
                                                "callback_data": "act|refresh",
                                            }
                                        ],
                                    ]
                                }

                            send_message(
                                target_chat,
                                msg,
                                reply_markup=markup,
                                message_thread_id=thread_id,
                            )
                    known_states[pid] = st

                for pid in list(known_states.keys()):
                    if pid not in current_pids:
                        del known_states[pid]
        except Exception as e:
            print(f"Error in watcher thread: {e}", file=sys.stderr)

        time.sleep(5)


def main():
    print("Iniciando Herdr Telegram Bot con Soporte de Temas Aislados...")

    for attempt in range(1, 6):
        res = setup_bot_commands()
        if res:
            break
        print(f"Esperando conexión a internet (intento {attempt}/5)...")
        time.sleep(3)

    agents, _ = get_agent_list_with_metadata()
    if agents and GROUP_CHAT_ID:
        for ag in agents:
            ws_label = ag.get("workspace_label")
            if ws_label:
                ensure_topic_for_workspace(ws_label)

    watcher = threading.Thread(target=state_watcher_thread, daemon=True)
    watcher.start()

    target_chat = GROUP_CHAT_ID if GROUP_CHAT_ID else ALLOWED_CHAT_ID
    send_message(
        target_chat,
        "🟢 <b>Herdr Bot con Temas Aislados activo.</b> Cada agente tiene su"
        " propio hilo de conversación independiente.",
        reply_markup=PERSISTENT_KEYBOARD,
    )

    offset = 0
    while True:
        try:
            url = f"{API_BASE}/getUpdates?offset={offset}&timeout=25"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=35) as resp:
                data = json.loads(resp.read().decode())
                if data.get("ok"):
                    for update in data.get("result", []):
                        offset = update["update_id"] + 1
                        if "message" in update:
                            process_message(update["message"])
                        elif "callback_query" in update:
                            handle_callback_query(update["callback_query"])
        except Exception as e:
            time.sleep(3)


if __name__ == "__main__":
    main()
