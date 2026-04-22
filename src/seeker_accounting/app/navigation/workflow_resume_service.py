from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from uuid import UUID, uuid4

from seeker_accounting.platform.exceptions.app_exceptions import ValidationError
from seeker_accounting.platform.exceptions.error_resolution import ResumeTokenPayload


class WorkflowResumeService:
    """In-memory store for workflow resume state during the running app session."""

    def __init__(self) -> None:
        self._tokens: dict[str, ResumeTokenPayload] = {}

    def create_token(
        self,
        workflow_key: str,
        payload: dict[str, object],
        origin_nav_id: str | None = None,
    ) -> str:
        normalized_payload = self._normalize_payload(payload)
        token = uuid4().hex
        self._tokens[token] = ResumeTokenPayload(
            workflow_key=workflow_key,
            origin_nav_id=origin_nav_id,
            payload=normalized_payload,
            created_at=datetime.now(timezone.utc),
        )
        return token

    def get_token(self, token: str) -> ResumeTokenPayload | None:
        stored = self._tokens.get(token)
        if stored is None:
            return None
        return replace(stored, payload=self._deep_copy_payload(stored.payload))

    def peek_token(self, token: str) -> ResumeTokenPayload | None:
        return self.get_token(token)

    def consume_token(self, token: str) -> ResumeTokenPayload | None:
        stored = self._tokens.pop(token, None)
        if stored is None:
            return None
        return replace(stored, payload=self._deep_copy_payload(stored.payload))

    def discard_token(self, token: str) -> bool:
        if token not in self._tokens:
            return False
        del self._tokens[token]
        return True

    def _normalize_payload(self, payload: dict[str, object]) -> dict[str, object]:
        if not isinstance(payload, dict):
            raise ValidationError("Workflow resume payload must be a dictionary.")
        try:
            normalized: dict[str, object] = self._normalize_value(payload)  # type: ignore[assignment]
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                "Workflow resume payload must contain only safe, serializable values. "
                "Widget references, service instances, and lambdas are not allowed."
            ) from exc
        return normalized

    def _normalize_value(self, value: object) -> object:
        if value is None or isinstance(value, (bool, int, float, str)):
            return value
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, UUID):
            return str(value)
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, dict):
            return {str(k): self._normalize_value(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._normalize_value(v) for v in value]
        # Reject anything else (widgets, services, arbitrary objects)
        raise TypeError(f"Unsupported value type in resume payload: {type(value).__name__!r}")

    def _deep_copy_payload(self, payload: dict[str, object]) -> dict[str, object]:
        # Payloads are normalized to JSON-safe primitives; round-trip is safe and cheap.
        return json.loads(json.dumps(payload))
