"""Structured logging via structlog with Rich console output."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import structlog

from desktop_agent.config import get_settings


def setup_logging(level: str | None = None) -> None:
    settings = get_settings()
    effective_level = level or settings.logging.level
    log_level = getattr(logging, effective_level.upper(), logging.INFO)

    # Ensure log directory exists
    log_path = Path(settings.logging.file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # File handler — always JSON for machine readability
    file_handler = logging.FileHandler(str(log_path), encoding="utf-8")
    file_handler.setLevel(log_level)

    # Stream handler — human-readable console
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(log_level)

    logging.basicConfig(
        format="%(message)s",
        level=log_level,
        handlers=[stream_handler, file_handler],
    )

    # Log OpenAI/httpx retry reasons at WARNING level
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if settings.logging.format == "json":
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )
    # Console gets human-readable output
    stream_handler.setFormatter(formatter)

    # File gets JSON for structured analysis
    json_formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
    )
    file_handler.setFormatter(json_formatter)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
