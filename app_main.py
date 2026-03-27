from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import sys
from typing import Any

from sts_ai_assistant.api.server import ApiServer
from sts_ai_assistant.config import AppConfig
from sts_ai_assistant.llm.openai_compatible import NullLLMClient, OpenAICompatibleLLMClient
from sts_ai_assistant.parsing.state_parser import StateParser, StateParserError
from sts_ai_assistant.service.assistant_service import AssistantService
from sts_ai_assistant.service.recommendation_engine import JsonlRecommendationSink, RecommendationEngine
from sts_ai_assistant.service.state_store import LatestStateStore
from sts_ai_assistant.transport.base import BaseTransport
from sts_ai_assistant.transport.socket_listener import SocketJsonTransport
from sts_ai_assistant.transport.stdio import CommunicationModStdioTransport


def parse_args(default_transport: str | None = None) -> argparse.Namespace:
    bootstrap = argparse.ArgumentParser(add_help=False)
    bootstrap.add_argument(
        "--config",
        default=None,
        help="Path to local JSON config file. Defaults to config/app_config.local.json if present.",
    )
    bootstrap_args, _ = bootstrap.parse_known_args()

    env_config = AppConfig.from_env(config_path=bootstrap_args.config)
    parser = argparse.ArgumentParser(
        description="Slay the Spire AI assistant scaffold",
        parents=[bootstrap],
    )
    parser.add_argument(
        "--transport",
        choices=("stdio", "socket"),
        default=default_transport or env_config.transport,
        help="State ingress transport.",
    )
    parser.add_argument("--host", default=env_config.host, help="Socket listener host.")
    parser.add_argument("--port", type=int, default=env_config.port, help="Socket listener port.")
    parser.add_argument(
        "--wait-frames",
        type=int,
        default=env_config.wait_frames,
        help="Frames for WAIT command in stdio mode.",
    )
    parser.add_argument("--log-level", default=env_config.log_level, help="Python logging level.")
    parser.add_argument("--log-file", default=str(env_config.log_file), help="Log file path.")
    parser.add_argument(
        "--recommendation-file",
        default=str(env_config.recommendation_file),
        help="Recommendation JSONL output path.",
    )
    parser.add_argument(
        "--current-state-file",
        default=str(env_config.current_state_file),
        help="Latest state JSON output path.",
    )
    parser.add_argument("--api-host", default=env_config.api_host, help="Local API host.")
    parser.add_argument("--api-port", type=int, default=env_config.api_port, help="Local API port.")
    parser.add_argument("--llm-base-url", default=env_config.llm_base_url)
    parser.add_argument("--llm-api-key", default=env_config.llm_api_key)
    parser.add_argument("--llm-model", default=env_config.llm_model)
    parser.add_argument("--openrouter-site-url", default=env_config.openrouter_site_url)
    parser.add_argument("--openrouter-app-name", default=env_config.openrouter_app_name)
    return parser.parse_args()


def configure_logging(level: str, log_file: Path) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [
        logging.StreamHandler(sys.stderr),
        logging.FileHandler(log_file, encoding="utf-8"),
    ]
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=handlers,
    )


def build_transport(args: argparse.Namespace) -> BaseTransport:
    if args.transport == "socket":
        return SocketJsonTransport(host=args.host, port=args.port)
    return CommunicationModStdioTransport(wait_frames=args.wait_frames)


def build_llm_client(args: argparse.Namespace) -> NullLLMClient | OpenAICompatibleLLMClient:
    if args.llm_base_url and args.llm_api_key and args.llm_model:
        return OpenAICompatibleLLMClient(
            base_url=args.llm_base_url.rstrip("/"),
            api_key=args.llm_api_key,
            model=args.llm_model,
            site_url=args.openrouter_site_url,
            app_name=args.openrouter_app_name,
        )
    return NullLLMClient()


def process_message(
    raw_message: str,
    parser: StateParser,
    engine: RecommendationEngine,
    assistant_service: AssistantService,
    state_store: LatestStateStore,
    logger: logging.Logger,
) -> dict[str, Any] | None:
    try:
        payload = json.loads(raw_message)
    except json.JSONDecodeError as exc:
        logger.warning("Invalid JSON received: %s | raw=%r", exc, raw_message[:300])
        return None

    try:
        snapshot = parser.parse_snapshot(payload)
    except StateParserError as exc:
        logger.warning("State parse skipped: %s", exc)
        return payload

    state_store.update_snapshot(snapshot)
    assistant_service.on_snapshot(snapshot)
    logger.info(
        "State received | screen=%s floor=%s asc=%s deck=%s relics=%s",
        snapshot.context.screen_type,
        snapshot.floor,
        snapshot.ascension_level,
        len(snapshot.deck),
        len(snapshot.relics),
    )

    try:
        recommendation = engine.maybe_recommend(snapshot)
    except Exception as exc:
        logger.warning("LLM recommendation failed: %s", exc)
        recommendation = None

    if recommendation is not None:
        state_store.update_recommendation(snapshot, recommendation)
        assistant_service.record_auto_recommendation(snapshot, recommendation)
        logger.info(
            "Recommendation emitted | screen=%s action=%s target=%s",
            recommendation.screen_type,
            recommendation.suggested_action,
            recommendation.primary_target,
        )

    return payload


def run(default_transport: str | None = None) -> int:
    args = parse_args(default_transport=default_transport)
    configure_logging(args.log_level, Path(args.log_file))
    logger = logging.getLogger("sts_ai_assistant")

    parser = StateParser()
    sink = JsonlRecommendationSink(Path(args.recommendation_file))
    state_store = LatestStateStore(Path(args.current_state_file))
    llm_client = build_llm_client(args)
    engine = RecommendationEngine(llm_client=llm_client, sink=sink)
    assistant_service = AssistantService(
        llm_client=llm_client,
        state_store=state_store,
        logger=logging.getLogger("sts_ai_assistant.assistant"),
    )
    transport = build_transport(args)
    api_server = ApiServer(
        host=args.api_host,
        port=args.api_port,
        state_store=state_store,
        assistant_service=assistant_service,
        logger=logging.getLogger("sts_ai_assistant.api"),
    )

    try:
        api_server.start()
        transport.start()
        for raw_message in transport.iter_messages():
            payload = process_message(
                raw_message,
                parser,
                engine,
                assistant_service,
                state_store,
                logger,
            )
            transport.after_message(payload)
    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
        return 0
    except Exception:
        logger.exception("Fatal runtime error.")
        return 1
    finally:
        api_server.close()
        transport.close()

    return 0


def main() -> int:
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
