from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class InterpretationItemDTO:
    interpretation_code: str
    title: str
    message: str
    basis_text: str
    severity_code: str
    detail_key: str | None = None


@dataclass(frozen=True, slots=True)
class InterpretationPanelDTO:
    title: str
    subtitle: str | None = None
    items: tuple[InterpretationItemDTO, ...] = field(default_factory=tuple)
