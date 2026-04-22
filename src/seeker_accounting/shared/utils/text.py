from __future__ import annotations


def humanize_identifier(value: str) -> str:
    cleaned = value.replace("_", " ").strip()
    return cleaned.title()


def truncate_text(value: str, limit: int = 80) -> str:
    if len(value) <= limit:
        return value
    return f"{value[: limit - 3].rstrip()}..."


def coalesce_text(value: str | None, fallback: str) -> str:
    return value.strip() if value and value.strip() else fallback
