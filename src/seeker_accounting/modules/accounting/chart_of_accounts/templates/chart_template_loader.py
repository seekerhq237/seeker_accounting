from __future__ import annotations

import csv
import json
from io import StringIO
from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as ET

from importlib.resources import files

from seeker_accounting.modules.accounting.chart_of_accounts.templates.chart_template_normalizer import (
    ChartTemplateNormalizationResult,
    ChartTemplateNormalizer,
)
from seeker_accounting.modules.accounting.chart_of_accounts.templates.chart_template_profile import (
    ChartTemplateProfile,
)
from seeker_accounting.modules.accounting.chart_of_accounts.templates.chart_template_row import (
    ChartTemplateRow,
)


class ChartTemplateLoader:
    def __init__(self, normalizer: ChartTemplateNormalizer | None = None) -> None:
        self._normalizer = normalizer or ChartTemplateNormalizer()

    def list_built_in_profiles(self) -> list[ChartTemplateProfile]:
        template_dir = files("seeker_accounting.resources.chart_templates")
        profiles = []
        for profile_path in template_dir.iterdir():
            if profile_path.name.endswith(".json"):
                profiles.append(self.load_built_in_profile(profile_path.name.removesuffix(".json")))
        return sorted(profiles, key=lambda profile: profile.display_name.lower())

    def load_built_in_profile(self, template_code: str) -> ChartTemplateProfile:
        template_dir = files("seeker_accounting.resources.chart_templates")
        payload = json.loads(template_dir.joinpath(f"{template_code}.json").read_text(encoding="utf-8"))
        return ChartTemplateProfile.from_dict(payload)

    def load_built_in_rows(self, template_code: str) -> list[ChartTemplateRow]:
        template_dir = files("seeker_accounting.resources.chart_templates")
        csv_text = template_dir.joinpath(f"{template_code}.csv").read_text(encoding="utf-8")
        reader = csv.DictReader(StringIO(csv_text))
        return [ChartTemplateRow.from_csv_row(row) for row in reader]

    def load_and_normalize_file(
        self,
        file_path: str,
        *,
        template_code: str = "external_import",
    ) -> ChartTemplateNormalizationResult:
        path = Path(file_path)
        suffix = path.suffix.lower()
        if suffix == ".csv":
            raw_rows = self._read_csv_rows(path)
        elif suffix == ".xlsx":
            raw_rows = self._read_xlsx_rows(path)
        else:
            raise ValueError(f"Unsupported chart template file type: {path.suffix}")

        return self._normalizer.normalize_rows(
            raw_rows,
            template_code=template_code,
            source_label=path.name,
        )

    def _read_csv_rows(self, path: Path) -> list[dict[str, str]]:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            return [self._normalize_raw_row(row) for row in reader]

    def _read_xlsx_rows(self, path: Path) -> list[dict[str, str]]:
        namespace = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        ns = {"x": namespace}

        with ZipFile(path) as archive:
            shared_strings = self._read_shared_strings(archive, namespace)
            workbook_root = ET.fromstring(archive.read("xl/workbook.xml"))
            sheet = workbook_root.find("x:sheets/x:sheet", ns)
            if sheet is None:
                return []

            rel_id = sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
            workbook_rels_root = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            sheet_target = None
            for relationship in workbook_rels_root:
                if relationship.attrib.get("Id") == rel_id:
                    sheet_target = relationship.attrib.get("Target")
                    break
            if sheet_target is None:
                return []

            sheet_root = ET.fromstring(archive.read(f"xl/{sheet_target}"))
            rows = []
            for row in sheet_root.findall(".//x:sheetData/x:row", ns):
                row_values: dict[int, str] = {}
                for cell in row.findall("x:c", ns):
                    reference = cell.attrib.get("r", "")
                    column_index = self._column_reference_to_number(reference)
                    value_node = cell.find("x:v", ns)
                    if value_node is None:
                        cell_value = ""
                    elif cell.attrib.get("t") == "s":
                        cell_value = shared_strings[int(value_node.text)]
                    else:
                        cell_value = value_node.text or ""
                    row_values[column_index] = cell_value
                if row_values:
                    rows.append(row_values)

        if not rows:
            return []

        max_column = max(max(row.keys()) for row in rows)
        materialized_rows = [
            [row.get(column_index, "") for column_index in range(1, max_column + 1)]
            for row in rows
        ]
        headers = [str(value).strip() for value in materialized_rows[0]]
        raw_rows = []
        for values in materialized_rows[1:]:
            if not any(str(value).strip() for value in values):
                continue
            raw_rows.append(
                self._normalize_raw_row(
                    {
                        headers[column_index]: str(values[column_index]).strip()
                        for column_index in range(len(headers))
                        if headers[column_index]
                    }
                )
            )
        return raw_rows

    def _read_shared_strings(self, archive: ZipFile, namespace: str) -> list[str]:
        shared_strings_path = "xl/sharedStrings.xml"
        if shared_strings_path not in archive.namelist():
            return []

        root = ET.fromstring(archive.read(shared_strings_path))
        values = []
        for item in root.findall(f"{{{namespace}}}si"):
            parts = [node.text or "" for node in item.iter(f"{{{namespace}}}t")]
            values.append("".join(parts))
        return values

    def _column_reference_to_number(self, reference: str) -> int:
        column_reference = "".join(character for character in reference if character.isalpha())
        total = 0
        for character in column_reference:
            total = total * 26 + (ord(character.upper()) - 64)
        return total

    def _normalize_raw_row(self, row: dict[str, str]) -> dict[str, str]:
        return {
            str(key).strip(): (str(value).strip() if value is not None else "")
            for key, value in row.items()
            if str(key).strip()
        }
