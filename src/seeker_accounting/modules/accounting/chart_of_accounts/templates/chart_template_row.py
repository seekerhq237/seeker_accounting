from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ChartTemplateRow:
    template_code: str
    account_code: str
    account_name: str
    parent_account_code: str | None
    level_no: int
    class_code: str
    class_name: str
    source_subaccount_code: str | None
    source_subaccount_name: str | None
    normal_balance: str
    allow_manual_posting: bool
    is_control_account_default: bool
    account_type_code: str
    notes: str | None = None
    is_active_default: bool = True

    @classmethod
    def csv_field_names(cls) -> tuple[str, ...]:
        return (
            "template_code",
            "account_code",
            "account_name",
            "parent_account_code",
            "level_no",
            "class_code",
            "class_name",
            "source_subaccount_code",
            "source_subaccount_name",
            "normal_balance",
            "allow_manual_posting",
            "is_control_account_default",
            "account_type_code",
            "notes",
            "is_active_default",
        )

    @classmethod
    def from_csv_row(cls, row: dict[str, str]) -> "ChartTemplateRow":
        return cls(
            template_code=row["template_code"].strip(),
            account_code=row["account_code"].strip(),
            account_name=row["account_name"].strip(),
            parent_account_code=(row.get("parent_account_code") or "").strip() or None,
            level_no=int(row["level_no"]),
            class_code=row["class_code"].strip(),
            class_name=row["class_name"].strip(),
            source_subaccount_code=(row.get("source_subaccount_code") or "").strip() or None,
            source_subaccount_name=(row.get("source_subaccount_name") or "").strip() or None,
            normal_balance=row["normal_balance"].strip().upper(),
            allow_manual_posting=(row["allow_manual_posting"].strip().lower() == "true"),
            is_control_account_default=(row["is_control_account_default"].strip().lower() == "true"),
            account_type_code=row["account_type_code"].strip(),
            notes=(row.get("notes") or "").strip() or None,
            is_active_default=(row["is_active_default"].strip().lower() == "true"),
        )

    def to_csv_row(self) -> dict[str, str]:
        return {
            "template_code": self.template_code,
            "account_code": self.account_code,
            "account_name": self.account_name,
            "parent_account_code": self.parent_account_code or "",
            "level_no": str(self.level_no),
            "class_code": self.class_code,
            "class_name": self.class_name,
            "source_subaccount_code": self.source_subaccount_code or "",
            "source_subaccount_name": self.source_subaccount_name or "",
            "normal_balance": self.normal_balance,
            "allow_manual_posting": "true" if self.allow_manual_posting else "false",
            "is_control_account_default": "true" if self.is_control_account_default else "false",
            "account_type_code": self.account_type_code,
            "notes": self.notes or "",
            "is_active_default": "true" if self.is_active_default else "false",
        }

