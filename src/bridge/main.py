"""Composition root and entry point for Herdr Telegram Bridge."""

import argparse
import logging
import signal
import sys
import time
from typing import Optional

from bridge.adapters.drivers.app_driver import HerdrAppDriver
from bridge.adapters.drivers.classic_driver import ClassicHerdrDriver
from bridge.adapters.drivers.composite_driver import CompositeHerdrDriver
from bridge.adapters.http.api_server import HttpApiServer
from bridge.adapters.persistence.json_topic_repository import JsonTopicRepository
from bridge.adapters.speech import SpeechTranscriber
from bridge.adapters.telegram.telegram_client import TelegramClient
from bridge.adapters.tunnel.cloudflared import CloudflareTunnel
from bridge.application.agent_service import AgentBridgeService
from bridge.application.bot_controller import BotController
from bridge.application.state_watcher import StateWatcher
from bridge.config import load_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("herdr-bridge")


def main(cli_args: Optional[list] = None):
    parser = argparse.ArgumentParser(description="Herdr Telegram Bridge Daemon")
    parser.add_argument(
        "--config",
        dest="config_path",
        default=None,
        help="Path to custom config.json file",
    )
    args = parser.parse_args(cli_args)

    logger.info("Initializing Herdr Telegram Bridge...")
    try:
        config = load_config(args.config_path)
    except Exception as e:
        logger.error("Configuration error: %s", e)
        sys.exit(1)

    logger.info(
        "Config loaded. Driver mode: '%s'. Whitelisted chat: %d",
        config.driver,
        config.allowed_chat_id,
    )

    # 1. Instantiate Adapters
    classic_driver = ClassicHerdrDriver(herdr_bin=config.herdr_bin)
    app_driver = HerdrAppDriver(
        herdr_app_bin=config.herdr_app_bin, hc_bin=config.hc_bin
    )
    composite_driver = CompositeHerdrDriver(
        classic_driver=classic_driver,
        app_driver=app_driver,
        preferred_mode=config.driver,
    )

    topic_repo = JsonTopicRepository(config.topics_file)
    telegram_client = TelegramClient(config.bot_token)

    # 2. Instantiate Application Services
    agent_service = AgentBridgeService(
        driver=composite_driver,
        topic_repo=topic_repo,
        telegram=telegram_client,
        allowed_chat_id=config.allowed_chat_id,
        group_chat_id=config.group_chat_id,
        projects_dir=config.projects_dir,
    )

    state_watcher = StateWatcher(
        service=agent_service,
        driver=composite_driver,
        topic_repo=topic_repo,
        telegram=telegram_client,
    )

    speech_transcriber = SpeechTranscriber(
        groq_api_key=config.groq_api_key,
        openai_api_key=config.openai_api_key,
    )

    # 3. Instantiate HTTP API Server & Cloudflare Tunnel (Mini App)
    http_server = HttpApiServer(
        service=agent_service,
        topic_repo=topic_repo,
        port=8765,
    )
    http_server.start()

    tunnel = CloudflareTunnel(local_port=8765)

    controller = BotController(
        service=agent_service,
        topic_repo=topic_repo,
        telegram=telegram_client,
        allowed_chat_id=config.allowed_chat_id,
        group_chat_id=config.group_chat_id,
        transcriber=speech_transcriber,
        tunnel=tunnel,
    )

    # Launch tunnel in background so bot starts polling immediately
    import threading

    def _start_tunnel():
        logger.info("Starting Cloudflare Tunnel for Telegram Mini App...")
        url = tunnel.start(timeout=20.0)
        if url:
            logger.info("Mini App is available online at: %s", url)
            ok = telegram_client.set_chat_menu_button(
                menu_button={"type": "web_app", "text": "Mini App", "web_app": {"url": url}}
            )
            if ok:
                logger.info("Telegram chat menu button configured with Mini App URL.")
        else:
            logger.warning("Could not obtain Cloudflare Tunnel URL.")

    threading.Thread(target=_start_tunnel, name="TunnelInitThread", daemon=True).start()

    bot_info = telegram_client.get_me()
    if bot_info:
        logger.info("Connected to Telegram as @%s (%s)", bot_info.get("username"), bot_info.get("first_name"))

    # 4. Setup Commands in Telegram
    telegram_client.set_my_commands([
        {"command": "status", "description": "Ver panel de todos los agentes (Desktop y Terminal)"},
        {"command": "app", "description": "Abrir la Mini App visual interactiva"},
        {"command": "result", "description": "Ver resultado final del agente"},
        {"command": "new", "description": "Crear un nuevo proyecto/espacio"},
        {"command": "resume", "description": "Reanudar sesión reteniendo contexto previo"},
        {"command": "read", "description": "Ver salida reciente de terminal"},
        {"command": "enter", "description": "Confirmar / Enviar Enter"},
        {"command": "yes", "description": "Responder Sí (y + Enter)"},
        {"command": "esc", "description": "Cancelar / Escape"},
        {"command": "close", "description": "Cerrar un proyecto o agente"},
        {"command": "help", "description": "Ver ayuda completa"},
    ])

    # 5. Graceful Shutdown Handlers
    def handle_exit(signum, frame):
        logger.info("Termination signal received. Shutting down gracefully...")
        state_watcher.stop()
        http_server.stop()
        tunnel.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    # 6. Start Background State Watcher
    state_watcher.start()

    # 7. Telegram Polling Loop
    logger.info("Bot polling loop running. Ready for incoming commands.")
    offset = None

    while True:
        try:
            updates = telegram_client.get_updates(offset=offset, timeout=25)
            for upd in updates:
                offset = upd.get("update_id", 0) + 1
                controller.process_update(upd)
        except Exception as e:
            logger.error("Error in main polling loop: %s", e)
            time.sleep(3)


if __name__ == "__main__":
    main()
