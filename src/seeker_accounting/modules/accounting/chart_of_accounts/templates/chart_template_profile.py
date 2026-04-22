from __future__ import annotations

from dataclasses import dataclass, field


BUILT_IN_TEMPLATE_CODE_OHADA = "ohada_syscohada_v1"


@dataclass(frozen=True, slots=True)
class ChartTemplateProfile:
    template_code: str
    display_name: str
    version: str
    description: str
    source_name: str
    source_format: str
    row_count: int
    notes: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "ChartTemplateProfile":
        notes = payload.get("notes", ())
        if not isinstance(notes, list | tuple):
            notes = ()
        return cls(
            template_code=str(payload["template_code"]),
            display_name=str(payload["display_name"]),
            version=str(payload["version"]),
            description=str(payload["description"]),
            source_name=str(payload["source_name"]),
            source_format=str(payload["source_format"]),
            row_count=int(payload["row_count"]),
            notes=tuple(str(note) for note in notes),
        )

