from __future__ import annotations

import csv
import json
from pathlib import Path

from seeker_accounting.modules.accounting.chart_of_accounts.templates.chart_template_loader import (
    ChartTemplateLoader,
)
from seeker_accounting.modules.accounting.chart_of_accounts.templates.chart_template_profile import (
    BUILT_IN_TEMPLATE_CODE_OHADA,
)
from seeker_accounting.modules.accounting.chart_of_accounts.templates.chart_template_row import (
    ChartTemplateRow,
)

DEFAULT_SOURCE_WORKBOOK = Path(r"C:\Users\User\Desktop\OHADA Chart of Accounts.xlsx")
DEFAULT_RESOURCE_DIR = Path("src/seeker_accounting/resources/chart_templates")


def main() -> int:
    loader = ChartTemplateLoader()
    normalization_result = loader.load_and_normalize_file(
        str(DEFAULT_SOURCE_WORKBOOK),
        template_code=BUILT_IN_TEMPLATE_CODE_OHADA,
    )

    DEFAULT_RESOURCE_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = DEFAULT_RESOURCE_DIR / f"{BUILT_IN_TEMPLATE_CODE_OHADA}.csv"
    json_path = DEFAULT_RESOURCE_DIR / f"{BUILT_IN_TEMPLATE_CODE_OHADA}.json"

    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ChartTemplateRow.csv_field_names())
        writer.writeheader()
        for row in normalization_result.normalized_rows:
            writer.writerow(row.to_csv_row())

    profile_payload = {
        "template_code": BUILT_IN_TEMPLATE_CODE_OHADA,
        "display_name": "OHADA SYSCOHADA",
        "version": "1.0",
        "description": (
            "Seeker Accounting canonical OHADA chart template normalized from the one-time "
            "source workbook and stored as app-owned internal resources."
        ),
        "source_name": DEFAULT_SOURCE_WORKBOOK.name,
        "source_format": "canonical_csv",
        "row_count": len(normalization_result.normalized_rows),
        "notes": [
            "Generated from the one-time OHADA workbook source; the runtime app does not depend on the workbook.",
            "Workbook correction applied: code 2451 'Animals' was normalized to 2464.",
            "Workbook correction applied: code 4821 'Tangible fixed assets' was normalized to 4822.",
            *normalization_result.warnings,
        ],
    }
    json_path.write_text(json.dumps(profile_payload, indent=2), encoding="utf-8")

    print("source_workbook", DEFAULT_SOURCE_WORKBOOK)
    print("normalized_rows", len(normalization_result.normalized_rows))
    print("duplicate_source_count", normalization_result.duplicate_source_count)
    print("invalid_row_count", normalization_result.invalid_row_count)
    print("csv_output", csv_path)
    print("json_output", json_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
