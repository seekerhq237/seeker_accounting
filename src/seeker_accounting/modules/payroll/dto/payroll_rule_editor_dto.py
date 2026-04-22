from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RuleEditorContextDTO:
    """Lightweight context DTO carried into the payroll rule bracket editor.

    Provides the display context (labels, counts) that the bracket editor needs
    without passing a full detail DTO or an ORM entity.
    """

    rule_set_id: int
    rule_code: str
    rule_name: str
    rule_type_code: str
    effective_from_label: str
    effective_to_label: str
    bracket_count: int
    is_active: bool
