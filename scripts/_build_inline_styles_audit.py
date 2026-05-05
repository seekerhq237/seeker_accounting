"""One-shot audit script for Phase 1 / Task A. Generates docs/ui_inline_styles_audit.md."""
from __future__ import annotations

import os
import re

ROOT = os.path.join("src", "seeker_accounting")
SKIP_FILES_IN_STYLES = {"tokens.py", "palette.py", "qss_builder.py"}
STYLES_DIR_FRAGMENT = os.sep + os.path.join("ui", "styles") + os.sep

PAT_HEX = re.compile(r"#[0-9A-Fa-f]{6}\b")
PAT_RGB = re.compile(r"\brgba?\(")
PAT_SET = re.compile(r"\bsetStyleSheet\b")


def main() -> None:
    entries: list[tuple[str, int, str]] = []
    for dirpath, _dirs, files in os.walk(ROOT):
        in_styles = STYLES_DIR_FRAGMENT in (dirpath + os.sep)
        for fname in files:
            if not fname.endswith(".py"):
                continue
            if in_styles and fname in SKIP_FILES_IN_STYLES:
                continue
            full = os.path.join(dirpath, fname)
            try:
                with open(full, "r", encoding="utf-8") as fh:
                    lines = fh.readlines()
            except (OSError, UnicodeDecodeError):
                continue
            for i, line in enumerate(lines, 1):
                if PAT_SET.search(line) or PAT_HEX.search(line) or PAT_RGB.search(line):
                    entries.append((full.replace("\\", "/"), i, line.rstrip("\n")))

    by_file: dict[str, list[tuple[int, str]]] = {}
    for path, line_no, line in entries:
        by_file.setdefault(path, []).append((line_no, line))

    out: list[str] = []
    out.append("# UI Inline Styles & Hardcoded Color Audit (Phase 1)")
    out.append("")
    out.append("Scope: every match of `setStyleSheet(`, hex color (`#RRGGBB`), or `rgb(`/`rgba(`")
    out.append("inside `src/seeker_accounting/**/*.py`, excluding the design-system files")
    out.append("(`shared/ui/styles/tokens.py`, `palette.py`, `qss_builder.py`).")
    out.append("")
    out.append("This is a catalogue only. **Do not** fix these as part of Phase 1 / Task A;")
    out.append("each entry should be migrated in later tasks to the new tokens / palette /")
    out.append("QSS rules introduced here.")
    out.append("")
    out.append("## Recommended replacement targets")
    out.append("")
    out.append("| Hardcoded pattern                  | Recommended replacement                                                                                  |")
    out.append("|------------------------------------|----------------------------------------------------------------------------------------------------------|")
    out.append("| status / chip color pairs          | `palette.status_<family>_{bg,fg,border}` via `QWidget#StatusChip[chipFamily=success|warning|danger|info|neutral|accent]` |")
    out.append("| toolbar / command surfaces         | `palette.command_bar_*` via `QWidget#CommandBar` / `QToolButton#CommandBarButton` / `QFrame#CommandBarSeparator`         |")
    out.append("| table header / row stripe colors   | `palette.data_table_*` via `QTableView#EnterpriseTable` + `QWidget#DataTableToolbar`                                     |")
    out.append("| generic surface / border           | existing `palette.{workspace_surface,secondary_surface,border_default,border_strong,divider_subtle}`                     |")
    out.append("| generic text                       | existing `palette.{text_primary,text_secondary,text_muted}`                                                              |")
    out.append("| accent / brand                     | existing `palette.{accent,accent_hover,accent_soft,accent_soft_strong,accent_text}`                                      |")
    out.append("| magic px sizes for chip/cmd/table  | corresponding new `SizeTokens` field (`chip_*`, `command_bar_*`, `data_table_*`)                                         |")
    out.append("")
    out.append(f"**Total flagged lines:** {len(entries)} across {len(by_file)} files.")
    out.append("")
    out.append("---")
    out.append("")

    for path in sorted(by_file):
        out.append(f"## `{path}`")
        out.append("")
        for line_no, line in by_file[path]:
            snippet = line.strip()
            if len(snippet) > 200:
                snippet = snippet[:197] + "..."
            # crude recommendation hint
            rec_parts: list[str] = []
            if "setStyleSheet" in snippet:
                rec_parts.append("move to QSS rule + objectName; reference palette/tokens")
            if PAT_HEX.search(snippet):
                rec_parts.append("replace hex with palette field")
            if PAT_RGB.search(snippet):
                rec_parts.append("replace rgb()/rgba() with palette field")
            rec_text = "; ".join(rec_parts) if rec_parts else "review"
            # escape backticks in snippet
            safe = snippet.replace("`", "\u02cb")
            out.append(f"- L{line_no}: `{safe}` -> {rec_text}")
        out.append("")

    target = os.path.join("docs", "ui_inline_styles_audit.md")
    with open(target, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out))
    print(f"WROTE {target}")
    print(f"TOTAL_ENTRIES={len(entries)}")
    print(f"FILES={len(by_file)}")


if __name__ == "__main__":
    main()
