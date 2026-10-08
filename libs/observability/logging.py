"""
Structured JSON logging and distributed tracing observability for Salon Payments Ops.
Compatible with Google Cloud Logging and Cloud Trace.
"""

import json
import logging
import os
import sys
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# Context variable for request correlation ID
correlation_id_ctx: ContextVar[str] = ContextVar("correlation_id", default="")


def get_correlation_id() -> str:
    cid = correlation_id_ctx.get()
    return cid if cid else str(uuid.uuid4())


def set_correlation_id(cid: str) -> None:
    correlation_id_ctx.set(cid)


class JsonFormatter(logging.Formatter):
    """Formats log records as structured JSON for Cloud Logging."""

    def __init__(self, service_name: str = "salon-payments-ops"):
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        log_entry: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "severity": record.levelname,
            "message": record.getMessage(),
            "service": self.service_name,
            "logger": record.name,
            "correlation_id": get_correlation_id(),
        }

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Merge extra fields if present
        if hasattr(record, "details") and isinstance(record.details, dict):
            log_entry["details"] = record.details

        return json.dumps(log_entry)


def setup_logger(service_name: str = "salon-payments-ops", log_level: str = "INFO") -> logging.Logger:
    """Configures structured JSON logging for standard stdout."""
    logger = logging.getLogger(service_name)
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(service_name=service_name))
    logger.addHandler(handler)
    logger.propagate = False
    return logger
