"""Centralised configuration with validation, TOML defaults, env overrides."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

load_dotenv()

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_TOML = _PROJECT_ROOT / "config" / "default.toml"


def _load_toml_defaults() -> dict:
    if _DEFAULT_TOML.exists():
        with open(_DEFAULT_TOML, "rb") as f:
            return tomllib.load(f)
    return {}


_DEFAULTS = _load_toml_defaults()


# ── Sub-models ───────────────────────────────────────────────────


class LLMConfig(BaseModel):
    planner_model: str = "deepseek/deepseek-v3.2"
    planner_base_url: str = "https://api.novita.ai/openai"
    planner_api_key: str = ""
    planner_max_tokens: int = 1024
    planner_temperature: float = 0.3

    executor_model: str = "qwen/qwen3-vl-235b-a22b-instruct"
    executor_base_url: str = "https://api.novita.ai/openai"
    executor_api_key: str = ""
    executor_max_tokens: int = 512
    executor_temperature: float = 0.1

    api_timeout: int = 45
    escalation_threshold: int = 3


class ScreenConfig(BaseModel):
    screenshot_quality: int = Field(75, ge=10, le=100)
    screenshot_format: Literal["png", "jpeg"] = "png"
    max_width: int = 1920
    max_height: int = 1080


class AgentConfig(BaseModel):
    max_steps: int = 50
    parallel_actions: bool = False


class MemoryConfig(BaseModel):
    vector_db_path: str = "data/vector_db"
    embedding_model: str = "all-MiniLM-L6-v2"
    max_short_term_actions: int = 50
    max_long_term_strategies: int = 500
    skill_library_path: str = "data/skills"


class AccessibilityConfig(BaseModel):
    enabled: bool = True
    fallback_to_vision: bool = True


class OCRConfig(BaseModel):
    enabled: bool = True
    engine: Literal["easyocr", "tesseract"] = "easyocr"
    languages: list[str] = Field(default_factory=lambda: ["en"])


class SchedulingConfig(BaseModel):
    enabled: bool = False
    timezone: str = "UTC"


class LoggingConfig(BaseModel):
    level: str = "INFO"
    format: Literal["console", "json"] = "console"
    file: str = "data/logs/agent.log"


class TTSConfig(BaseModel):
    enabled: bool = True
    voice: str = "Samantha"
    rate: int = 220  # words per minute


# ── Root Settings ────────────────────────────────────────────────


class Settings(BaseSettings):
    """Application settings.  Priority: env vars > .env > default.toml."""

    llm: LLMConfig = Field(default_factory=lambda: LLMConfig(**_DEFAULTS.get("llm", {})))
    screen: ScreenConfig = Field(default_factory=lambda: ScreenConfig(**_DEFAULTS.get("screen", {})))
    agent: AgentConfig = Field(default_factory=lambda: AgentConfig(**_DEFAULTS.get("agent", {})))
    memory: MemoryConfig = Field(
        default_factory=lambda: MemoryConfig(**_DEFAULTS.get("memory", {}))
    )
    accessibility: AccessibilityConfig = Field(
        default_factory=lambda: AccessibilityConfig(**_DEFAULTS.get("accessibility", {}))
    )
    ocr: OCRConfig = Field(default_factory=lambda: OCRConfig(**_DEFAULTS.get("ocr", {})))
    scheduling: SchedulingConfig = Field(
        default_factory=lambda: SchedulingConfig(**_DEFAULTS.get("scheduling", {}))
    )
    logging: LoggingConfig = Field(
        default_factory=lambda: LoggingConfig(**_DEFAULTS.get("logging", {}))
    )
    tts: TTSConfig = Field(
        default_factory=lambda: TTSConfig(**_DEFAULTS.get("tts", {}))
    )

    model_config = {"env_prefix": "AGENT_", "env_nested_delimiter": "__"}

    def resolve_api_keys(self) -> None:
        """Read PLANNER_API_KEY and EXECUTOR_API_KEY from env.
        Falls back to OPENAI_API_KEY if a specific key is not set.
        """
        openai_key = os.getenv("OPENAI_API_KEY", "")

        if not self.llm.planner_api_key:
            self.llm.planner_api_key = os.getenv("PLANNER_API_KEY", openai_key)
        if not self.llm.executor_api_key:
            self.llm.executor_api_key = os.getenv("EXECUTOR_API_KEY", openai_key)


# ── Singleton ────────────────────────────────────────────────────

_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
        _settings.resolve_api_keys()
    return _settings


def reload_settings() -> Settings:
    global _settings
    _settings = None
    return get_settings()
