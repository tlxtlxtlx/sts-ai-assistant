from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class AppConfig:
    transport: str = "stdio"
    host: str = "127.0.0.1"
    port: int = 5123
    wait_frames: int = 30
    log_level: str = "INFO"
    log_file: Path = Path("logs/sts_ai_assistant.log")
    recommendation_file: Path = Path("logs/recommendations.jsonl")
    current_state_file: Path = Path("logs/current_state.json")
    api_host: str = "127.0.0.1"
    api_port: int = 8765
    llm_base_url: str | None = "https://openrouter.ai/api/v1"
    llm_api_key: str | None = None
    llm_model: str | None = "stepfun/step-3.5-flash:free"
    openrouter_site_url: str = "http://127.0.0.1:5173"
    openrouter_app_name: str = "STS AI Assistant"

    @classmethod
    def from_env(cls, config_path: str | os.PathLike[str] | None = None) -> "AppConfig":
        file_values = cls._load_file_values(config_path)
        return cls(
            transport=cls._get_text(
                "STS_TRANSPORT", file_values, "transport", default="stdio"
            ).lower(),
            host=cls._get_text(
                "STS_SOCKET_HOST", file_values, "socket_host", default="127.0.0.1"
            ),
            port=cls._get_int("STS_SOCKET_PORT", file_values, "socket_port", default=5123),
            wait_frames=cls._get_int(
                "STS_WAIT_FRAMES", file_values, "wait_frames", default=30
            ),
            log_level=cls._get_text(
                "STS_LOG_LEVEL", file_values, "log_level", default="INFO"
            ).upper(),
            log_file=Path(
                cls._get_text(
                    "STS_LOG_FILE",
                    file_values,
                    "log_file",
                    default="logs/sts_ai_assistant.log",
                )
            ),
            recommendation_file=Path(
                cls._get_text(
                    "STS_RECOMMENDATION_FILE",
                    file_values,
                    "recommendation_file",
                    default="logs/recommendations.jsonl",
                )
            ),
            current_state_file=Path(
                cls._get_text(
                    "STS_CURRENT_STATE_FILE",
                    file_values,
                    "current_state_file",
                    default="logs/current_state.json",
                )
            ),
            api_host=cls._get_text(
                "STS_API_HOST", file_values, "api_host", default="127.0.0.1"
            ),
            api_port=cls._get_int("STS_API_PORT", file_values, "api_port", default=8765),
            llm_base_url=cls._get_optional_text(
                "STS_LLM_BASE_URL",
                file_values,
                "llm_base_url",
                default="https://openrouter.ai/api/v1",
            ),
            llm_api_key=cls._get_optional_text("STS_LLM_API_KEY", file_values, "llm_api_key"),
            llm_model=cls._get_optional_text(
                "STS_LLM_MODEL",
                file_values,
                "llm_model",
                default="stepfun/step-3.5-flash:free",
            ),
            openrouter_site_url=cls._get_text(
                "STS_OPENROUTER_SITE_URL",
                file_values,
                "openrouter_site_url",
                default="http://127.0.0.1:5173",
            ),
            openrouter_app_name=cls._get_text(
                "STS_OPENROUTER_APP_NAME",
                file_values,
                "openrouter_app_name",
                default="STS AI Assistant",
            ),
        )

    @classmethod
    def _load_file_values(
        cls, config_path: str | os.PathLike[str] | None
    ) -> dict[str, Any]:
        path = cls._resolve_config_path(config_path)
        if path is None:
            return {}

        with path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)

        if not isinstance(raw, dict):
            raise ValueError(f"Config file must contain a JSON object: {path}")

        return {
            "transport": cls._first_present(raw, ("transport", "mode"), "transport"),
            "socket_host": cls._first_present(raw, ("transport", "host"), "socket_host", "host"),
            "socket_port": cls._first_present(raw, ("transport", "port"), "socket_port", "port"),
            "wait_frames": cls._first_present(
                raw, ("transport", "wait_frames"), "wait_frames"
            ),
            "log_level": cls._first_present(raw, ("logging", "level"), "log_level"),
            "log_file": cls._first_present(raw, ("logging", "file"), "log_file"),
            "recommendation_file": cls._first_present(
                raw, ("output", "recommendation_file"), "recommendation_file"
            ),
            "current_state_file": cls._first_present(
                raw, ("output", "current_state_file"), "current_state_file"
            ),
            "api_host": cls._first_present(raw, ("api", "host"), "api_host"),
            "api_port": cls._first_present(raw, ("api", "port"), "api_port"),
            "llm_base_url": cls._first_present(raw, ("llm", "base_url"), "llm_base_url"),
            "llm_api_key": cls._first_present(raw, ("llm", "api_key"), "llm_api_key"),
            "llm_model": cls._first_present(raw, ("llm", "model"), "llm_model"),
            "openrouter_site_url": cls._first_present(
                raw, ("llm", "site_url"), "openrouter_site_url"
            ),
            "openrouter_app_name": cls._first_present(
                raw, ("llm", "app_name"), "openrouter_app_name"
            ),
        }

    @staticmethod
    def _resolve_config_path(config_path: str | os.PathLike[str] | None) -> Path | None:
        candidates: list[Path] = []
        if config_path:
            candidates.append(Path(config_path))
        env_path = os.getenv("STS_CONFIG_FILE")
        if env_path:
            candidates.append(Path(env_path))
        candidates.extend(
            [
                Path("config/app_config.local.json"),
                Path("config/app_config.json"),
            ]
        )

        seen: set[Path] = set()
        for candidate in candidates:
            resolved = Path(candidate)
            if resolved in seen:
                continue
            seen.add(resolved)
            if resolved.exists():
                return resolved
        return None

    @staticmethod
    def _first_present(raw: dict[str, Any], *candidates: str | tuple[str, ...]) -> Any:
        missing = object()
        for candidate in candidates:
            if isinstance(candidate, tuple):
                value: Any = raw
                for key in candidate:
                    if not isinstance(value, dict) or key not in value:
                        value = missing
                        break
                    value = value[key]
            else:
                value = raw.get(candidate, missing)
            if value is not missing and value is not None:
                return value
        return None

    @staticmethod
    def _get_optional_text(
        env_name: str,
        file_values: dict[str, Any],
        file_key: str,
        default: str | None = None,
    ) -> str | None:
        value = os.getenv(env_name)
        if value is None:
            value = file_values.get(file_key, default)
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @classmethod
    def _get_text(
        cls,
        env_name: str,
        file_values: dict[str, Any],
        file_key: str,
        default: str,
    ) -> str:
        return cls._get_optional_text(env_name, file_values, file_key, default=default) or default

    @staticmethod
    def _get_int(
        env_name: str,
        file_values: dict[str, Any],
        file_key: str,
        default: int,
    ) -> int:
        value = os.getenv(env_name)
        if value is None:
            value = file_values.get(file_key)
        if value is None:
            value = default
        return int(value)
