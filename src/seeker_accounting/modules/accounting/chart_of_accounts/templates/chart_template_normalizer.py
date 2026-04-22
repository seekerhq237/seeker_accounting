from __future__ import annotations

from dataclasses import dataclass, field

from seeker_accounting.modules.accounting.chart_of_accounts.seeds.global_chart_reference_seed import (
    ACCOUNT_CLASS_NAME_BY_CODE,
)
from seeker_accounting.modules.accounting.chart_of_accounts.templates.chart_template_row import (
    ChartTemplateRow,
)

_WORKBOOK_DUPLICATE_OVERRIDES = {
    ("2451", "Animals"): ("2464", "Duplicate source code corrected into the biological assets range."),
    ("4821", "Tangible fixed assets"): ("4822", "Duplicate source code corrected to preserve the bills-payable series."),
}

_CANONICAL_ALIASES = {
    "account_code": ("account_code", "account code", "accnumber", "code"),
    "account_name": ("account_name", "account name", "accname", "name"),
    "parent_account_code": ("parent_account_code", "parent account code", "parent_code", "subaccnum"),
    "class_code": ("class_code", "class code", "class#", "class_no"),
    "class_name": ("class_name", "class name", "class"),
    "source_subaccount_code": ("source_subaccount_code", "source subaccount code", "subaccnum"),
    "source_subaccount_name": ("source_subaccount_name", "source subaccount name", "subacc"),
    "normal_balance": ("normal_balance", "normal balance"),
    "allow_manual_posting": ("allow_manual_posting", "allow manual posting"),
    "is_control_account_default": ("is_control_account_default", "is control account default"),
    "account_type_code": ("account_type_code", "account type code"),
    "notes": ("notes", "note"),
    "is_active_default": ("is_active_default", "is active default"),
    "level_no": ("level_no", "level no", "level"),
}


@dataclass(frozen=True, slots=True)
class ChartTemplateNormalizationResult:
    source_label: str
    template_code: str
    total_source_rows: int
    normalized_rows: tuple[ChartTemplateRow, ...]
    duplicate_source_count: int
    invalid_row_count: int
    warnings: tuple[str, ...] = field(default_factory=tuple)


class ChartTemplateNormalizer:
    def normalize_rows(
        self,
        raw_rows: list[dict[str, str]],
        *,
        template_code: str,
        source_label: str,
    ) -> ChartTemplateNormalizationResult:
        if not raw_rows:
            return ChartTemplateNormalizationResult(
                source_label=source_label,
                template_code=template_code,
                total_source_rows=0,
                normalized_rows=(),
                duplicate_source_count=0,
                invalid_row_count=0,
                warnings=("The source file did not contain any chart rows.",),
            )

        workbook_headers = {self._normalize_header_name(key) for key in raw_rows[0]}
        if {"class", "accnumber", "accname", "subaccnum"}.issubset(workbook_headers):
            return self._normalize_ohada_workbook_rows(
                raw_rows,
                template_code=template_code,
                source_label=source_label,
            )

        return self._normalize_canonical_like_rows(
            raw_rows,
            template_code=template_code,
            source_label=source_label,
        )

    def _normalize_ohada_workbook_rows(
        self,
        raw_rows: list[dict[str, str]],
        *,
        template_code: str,
        source_label: str,
    ) -> ChartTemplateNormalizationResult:
        base_rows: list[dict[str, object]] = []
        warnings: list[str] = []
        invalid_row_count = 0

        for row_number, raw_row in enumerate(raw_rows, start=2):
            class_name = self._clean_text(raw_row.get("Class", ""))
            class_code = self._extract_class_code(raw_row.get("Class#", ""))
            account_code = self._canonicalize_code(raw_row.get("AccNumber", ""))
            account_name = self._clean_text(raw_row.get("AccName", ""))
            source_subaccount_code = self._canonicalize_code(raw_row.get("SubAccNum", ""), allow_blank=True)
            source_subaccount_name = self._clean_text(raw_row.get("SubAcc", ""))

            if not account_code or not account_name:
                invalid_row_count += 1
                warnings.append(f"Skipped row {row_number}: account code or account name was blank.")
                continue

            correction_note: str | None = None
            override = _WORKBOOK_DUPLICATE_OVERRIDES.get((account_code, account_name))
            if override is not None:
                account_code, correction_note = override

            class_code = class_code or account_code[:1]
            class_name = class_name or ACCOUNT_CLASS_NAME_BY_CODE.get(class_code, "Unclassified")
            account_type_code = self._derive_account_type_code(account_code, class_code)
            normal_balance = self._derive_normal_balance(account_code, class_code, account_type_code)

            base_rows.append(
                {
                    "template_code": template_code,
                    "account_code": account_code,
                    "account_name": account_name,
                    "class_code": class_code,
                    "class_name": class_name,
                    "source_subaccount_code": source_subaccount_code,
                    "source_subaccount_name": source_subaccount_name or None,
                    "normal_balance": normal_balance,
                    "allow_manual_posting": None,
                    "is_control_account_default": False,
                    "account_type_code": account_type_code,
                    "notes": correction_note,
                    "is_active_default": True,
                    "explicit_parent_account_code": None,
                    "explicit_level_no": None,
                }
            )

        return self._finalize_rows(
            base_rows,
            total_source_rows=len(raw_rows),
            template_code=template_code,
            source_label=source_label,
            invalid_row_count=invalid_row_count,
            warnings=warnings,
        )

    def _normalize_canonical_like_rows(
        self,
        raw_rows: list[dict[str, str]],
        *,
        template_code: str,
        source_label: str,
    ) -> ChartTemplateNormalizationResult:
        base_rows: list[dict[str, object]] = []
        warnings: list[str] = []
        invalid_row_count = 0

        for row_number, raw_row in enumerate(raw_rows, start=2):
            account_code = self._canonicalize_code(self._extract_value(raw_row, "account_code"))
            account_name = self._clean_text(self._extract_value(raw_row, "account_name"))
            if not account_code or not account_name:
                invalid_row_count += 1
                warnings.append(f"Skipped row {row_number}: account code or account name was blank.")
                continue

            class_code = self._canonicalize_code(self._extract_value(raw_row, "class_code"), allow_blank=True)
            if not class_code:
                class_code = account_code[:1]
            class_name = self._clean_text(self._extract_value(raw_row, "class_name")) or ACCOUNT_CLASS_NAME_BY_CODE.get(
                class_code,
                "Unclassified",
            )
            account_type_code = self._canonicalize_code(
                self._extract_value(raw_row, "account_type_code"),
                allow_blank=True,
            )
            if not account_type_code:
                account_type_code = self._derive_account_type_code(account_code, class_code)
            normal_balance = self._canonicalize_code(
                self._extract_value(raw_row, "normal_balance"),
                allow_blank=True,
            )
            if not normal_balance:
                normal_balance = self._derive_normal_balance(account_code, class_code, account_type_code)

            base_rows.append(
                {
                    "template_code": template_code,
                    "account_code": account_code,
                    "account_name": account_name,
                    "class_code": class_code,
                    "class_name": class_name,
                    "source_subaccount_code": self._canonicalize_code(
                        self._extract_value(raw_row, "source_subaccount_code"),
                        allow_blank=True,
                    ),
                    "source_subaccount_name": self._clean_text(self._extract_value(raw_row, "source_subaccount_name")) or None,
                    "normal_balance": normal_balance,
                    "allow_manual_posting": self._parse_optional_bool(self._extract_value(raw_row, "allow_manual_posting")),
                    "is_control_account_default": self._parse_optional_bool(
                        self._extract_value(raw_row, "is_control_account_default")
                    ),
                    "account_type_code": account_type_code.lower(),
                    "notes": self._clean_text(self._extract_value(raw_row, "notes")) or None,
                    "is_active_default": self._parse_optional_bool(self._extract_value(raw_row, "is_active_default")),
                    "explicit_parent_account_code": self._canonicalize_code(
                        self._extract_value(raw_row, "parent_account_code"),
                        allow_blank=True,
                    ),
                    "explicit_level_no": self._parse_optional_int(self._extract_value(raw_row, "level_no")),
                }
            )

        return self._finalize_rows(
            base_rows,
            total_source_rows=len(raw_rows),
            template_code=template_code,
            source_label=source_label,
            invalid_row_count=invalid_row_count,
            warnings=warnings,
        )

    def _finalize_rows(
        self,
        base_rows: list[dict[str, object]],
        *,
        total_source_rows: int,
        template_code: str,
        source_label: str,
        invalid_row_count: int,
        warnings: list[str],
    ) -> ChartTemplateNormalizationResult:
        rows_by_code: dict[str, dict[str, object]] = {}
        duplicate_source_count = 0

        for row in base_rows:
            account_code = str(row["account_code"])
            existing = rows_by_code.get(account_code)
            if existing is None:
                rows_by_code[account_code] = row
                continue

            duplicate_source_count += 1
            if str(existing["account_name"]).strip() != str(row["account_name"]).strip():
                warnings.append(
                    f"Skipped duplicate source account code {account_code}: conflicting names "
                    f"'{existing['account_name']}' and '{row['account_name']}'."
                )
            else:
                warnings.append(f"Skipped duplicate source account code {account_code}.")

        all_codes = set(rows_by_code)
        child_counts = {code: 0 for code in all_codes}
        parent_cache: dict[str, str | None] = {}
        level_cache: dict[str, int] = {}

        for code, row in rows_by_code.items():
            explicit_parent = row.get("explicit_parent_account_code")
            parent_code = str(explicit_parent) if explicit_parent else self._infer_parent_account_code(code, all_codes)
            if parent_code:
                child_counts[parent_code] = child_counts.get(parent_code, 0) + 1
            parent_cache[code] = parent_code

        def resolve_level(account_code: str) -> int:
            cached = level_cache.get(account_code)
            if cached is not None:
                return cached

            explicit_level = rows_by_code[account_code].get("explicit_level_no")
            if isinstance(explicit_level, int) and explicit_level > 0:
                level_cache[account_code] = explicit_level
                return explicit_level

            parent_code = parent_cache.get(account_code)
            if not parent_code:
                level_cache[account_code] = 1
                return 1

            level = resolve_level(parent_code) + 1 if parent_code in rows_by_code else 2
            level_cache[account_code] = level
            return level

        normalized_rows = []
        for code, row in sorted(rows_by_code.items(), key=lambda item: (len(item[0]), item[0])):
            parent_code = parent_cache.get(code)
            allow_manual_posting = row.get("allow_manual_posting")
            if not isinstance(allow_manual_posting, bool):
                allow_manual_posting = child_counts.get(code, 0) == 0

            is_control_account_default = row.get("is_control_account_default")
            if not isinstance(is_control_account_default, bool):
                is_control_account_default = False

            is_active_default = row.get("is_active_default")
            if not isinstance(is_active_default, bool):
                is_active_default = True

            normalized_rows.append(
                ChartTemplateRow(
                    template_code=template_code,
                    account_code=code,
                    account_name=str(row["account_name"]),
                    parent_account_code=parent_code,
                    level_no=resolve_level(code),
                    class_code=str(row["class_code"]),
                    class_name=str(row["class_name"]),
                    source_subaccount_code=(
                        str(row["source_subaccount_code"])
                        if row.get("source_subaccount_code")
                        else None
                    ),
                    source_subaccount_name=(
                        str(row["source_subaccount_name"])
                        if row.get("source_subaccount_name")
                        else None
                    ),
                    normal_balance=str(row["normal_balance"]).upper(),
                    allow_manual_posting=allow_manual_posting,
                    is_control_account_default=is_control_account_default,
                    account_type_code=str(row["account_type_code"]).lower(),
                    notes=str(row["notes"]) if row.get("notes") else None,
                    is_active_default=is_active_default,
                )
            )

        return ChartTemplateNormalizationResult(
            source_label=source_label,
            template_code=template_code,
            total_source_rows=total_source_rows,
            normalized_rows=tuple(normalized_rows),
            duplicate_source_count=duplicate_source_count,
            invalid_row_count=invalid_row_count,
            warnings=tuple(warnings),
        )

    def _extract_value(self, raw_row: dict[str, str], field_name: str) -> str:
        for key, value in raw_row.items():
            normalized_key = self._normalize_header_name(key)
            if normalized_key in _CANONICAL_ALIASES[field_name]:
                return value or ""
        return ""

    def _normalize_header_name(self, value: str) -> str:
        return "".join(ch for ch in value.strip().lower() if ch.isalnum() or ch == "_")

    def _clean_text(self, value: str) -> str:
        return " ".join((value or "").split())

    def _canonicalize_code(self, value: str, allow_blank: bool = False) -> str:
        normalized = "".join(ch for ch in (value or "").strip().upper() if ch not in {" ", "\t"})
        if allow_blank:
            return normalized
        return normalized

    def _extract_class_code(self, value: str) -> str:
        digits = "".join(ch for ch in (value or "") if ch.isdigit())
        return digits

    def _infer_parent_account_code(self, account_code: str, all_codes: set[str]) -> str | None:
        for length in range(len(account_code) - 1, 1, -1):
            candidate = account_code[:length]
            if candidate in all_codes:
                return candidate
        return None

    def _parse_optional_bool(self, value: str) -> bool | None:
        normalized = (value or "").strip().lower()
        if not normalized:
            return None
        if normalized in {"1", "true", "yes", "y"}:
            return True
        if normalized in {"0", "false", "no", "n"}:
            return False
        return None

    def _parse_optional_int(self, value: str) -> int | None:
        normalized = (value or "").strip()
        if not normalized:
            return None
        try:
            return int(normalized)
        except ValueError:
            return None

    def _derive_account_type_code(self, account_code: str, class_code: str) -> str:
        if class_code == "1":
            return "equity" if account_code[:2] in {"10", "11", "12", "13", "14"} else "noncurrent_liability"
        if class_code == "2":
            return "contra_noncurrent_asset" if account_code.startswith(("28", "29")) else "noncurrent_asset"
        if class_code == "3":
            return "contra_inventory_asset" if account_code.startswith("39") else "inventory_asset"
        if class_code == "4":
            return "contra_third_party" if account_code.startswith("49") else "third_party"
        if class_code == "5":
            return "contra_treasury_asset" if account_code.startswith("59") else "treasury_asset"
        if class_code == "6":
            return "expense"
        if class_code == "7":
            return "revenue"
        if class_code == "8":
            return "other_revenue" if account_code[:2] in {"82", "84", "86", "88"} else "other_expense"
        return "contingency_management"

    def _derive_normal_balance(self, account_code: str, class_code: str, account_type_code: str) -> str:
        if account_type_code in {
            "equity",
            "noncurrent_liability",
            "contra_noncurrent_asset",
            "contra_inventory_asset",
            "contra_third_party",
            "contra_treasury_asset",
            "revenue",
            "other_revenue",
        }:
            return "CREDIT"

        if class_code == "4":
            if account_code.startswith(("40", "42", "43", "44", "481", "482", "484")):
                return "CREDIT"
            if account_code.startswith(("41", "45", "46", "47", "485", "488")):
                return "DEBIT"

        return "DEBIT"
