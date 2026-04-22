from __future__ import annotations

from enum import StrEnum


class StatusCode(StrEnum):
    READY = "ready"
    PLACEHOLDER = "placeholder"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"

