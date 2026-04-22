from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TemplatePreviewDTO:
    """Metadata passed to the template-preview dialog framework."""

    template_code: str
    template_title: str
    description: str
    standard_note: str
