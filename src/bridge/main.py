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
from bridge.adapters.persistence.json_topic_repository import JsonTopicRepository
from bridge.adapters.speech import SpeechTranscriber
from bridge.adapters.telegram.telegram_client import TelegramClient
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

    controller = BotController(
        service=agent_service,
        topic_repo=topic_repo,
        telegram=telegram_client,
        allowed_chat_id=config.allowed_chat_id,
        group_chat_id=config.group_chat_id,
        transcriber=speech_transcriber,
    )

    # 3. Setup Commands in Telegram
    telegram_client.set_my_commands([
        {"command": "status", "description": "Ver panel de todos los agentes (Desktop y Terminal)"},
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

    # 4. Graceful Shutdown Handlers
    def handle_exit(signum, frame):
        logger.info("Termination signal received. Shutting down gracefully...")
        state_watcher.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    # 5. Start Background State Watcher
    state_watcher.start()

    # 6. Telegram Polling Loop
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
