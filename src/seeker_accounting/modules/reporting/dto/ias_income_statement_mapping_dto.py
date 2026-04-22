from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class IasIncomeStatementSectionDTO:
    statement_profile_code: str
    section_code: str
    section_label: str
    parent_section_code: str | None
    display_order: int
    row_kind_code: str
    is_mapping_target: bool
    is_formula: bool
    display_path: str
    indent_level: int
    aggregation_components: tuple[str, ...] = ()
    formula_components: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class IasIncomeStatementAccountOptionDTO:
    account_id: int
    account_code: str
    account_name: str
    account_class_code: str | None
    account_type_code: str | None
    account_type_section_code: str | None
    normal_balance: str
    allow_manual_posting: bool
    is_control_account: bool
    is_active: bool
    default_sign_behavior_code: str
    mapped_mapping_id: int | None = None
    mapped_section_code: str | None = None
    mapped_subsection_code: str | None = None
    mapped_sign_behavior_code: str | None = None
    mapped_display_order: int | None = None
    mapped_is_active: bool | None = None


@dataclass(frozen=True, slots=True)
class IasIncomeStatementMappingDTO:
    id: int
    company_id: int
    statement_profile_code: str
    section_code: str
    section_label: str
    subsection_code: str | None
    subsection_label: str | None
    account_id: int
    account_code: str
    account_name: str
    account_class_code: str | None
    account_type_code: str | None
    account_type_section_code: str | None
    normal_balance: str
    allow_manual_posting: bool
    is_control_account: bool
    account_is_active: bool
    sign_behavior_code: str
    default_sign_behavior_code: str
    display_order: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    created_by_user_id: int | None
    updated_by_user_id: int | None


@dataclass(frozen=True, slots=True)
class IasIncomeStatementValidationIssueDTO:
    issue_code: str
    severity_code: str
    title: str
    message: str
    account_id: int | None = None
    account_code: str | None = None
    section_code: str | None = None
    subsection_code: str | None = None
    mapping_id: int | None = None


@dataclass(frozen=True, slots=True)
class IasIncomeStatementMappingEditorDTO:
    company_id: int
    statement_profile_code: str
    sections: tuple[IasIncomeStatementSectionDTO, ...]
    account_options: tuple[IasIncomeStatementAccountOptionDTO, ...]
    mappings: tuple[IasIncomeStatementMappingDTO, ...]
    issues: tuple[IasIncomeStatementValidationIssueDTO, ...] = field(default_factory=tuple)
    unmapped_relevant_accounts: tuple[IasIncomeStatementAccountOptionDTO, ...] = field(default_factory=tuple)
    has_mappings: bool = False
    has_issues: bool = False


@dataclass(frozen=True, slots=True)
class UpsertIasIncomeStatementMappingCommand:
    section_code: str
    subsection_code: str | None
    account_ids: tuple[int, ...]
    sign_behavior_code: str | None = None
    display_order: int = 10
    is_active: bool = True


@dataclass(frozen=True, slots=True)
class ToggleIasIncomeStatementMappingStateCommand:
    mapping_id: int
    is_active: bool

