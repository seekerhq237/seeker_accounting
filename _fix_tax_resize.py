"""Add layout tokens and apply_window_size for tax_compliance_dialogs.py."""
from __future__ import annotations
import re
from pathlib import Path

BASE = Path("src/seeker_accounting")
LAYOUT = BASE / "shared" / "ui" / "layout_constraints.py"
DIALOGS = BASE / "modules" / "taxation" / "ui" / "tax_compliance_dialogs.py"

# Tokens to add: (key_suffix, width, height, old_resize_str)
NEW_TOKENS = [
    ("modules.taxation.ui.tax.compliance.dialogs.0",  520, 320, "self.resize(520, 320)"),  # GenerateMonthlyVATObligationsDialog
    ("modules.taxation.ui.tax.compliance.dialogs.1",  520, 320, None),                     # GenerateQuarterlyCITInstallmentsDialog (same dims)
    ("modules.taxation.ui.tax.compliance.dialogs.2",  560, 360, "self.resize(560, 360)"),  # FileTaxReturnDialog
    ("modules.taxation.ui.tax.compliance.dialogs.3",  560, 420, "self.resize(560, 420)"),  # FileAssessedTaxReturnDialog
    ("modules.taxation.ui.tax.compliance.dialogs.4",  560, 460, "self.resize(560, 460)"),  # RecordTaxPaymentDialog
    ("modules.taxation.ui.tax.compliance.dialogs.5",  640, 540, "self.resize(640, 540)"),  # DSFExportDialog
    ("modules.taxation.ui.tax.compliance.dialogs.6",  720, 560, "self.resize(720, 560)"),  # SettleVATReturnDialog
    ("modules.taxation.ui.tax.compliance.dialogs.7",  520, 320, None),                     # GenerateMonthlyWithholdingObligationsDialog (same as 0)
    ("modules.taxation.ui.tax.compliance.dialogs.8",  520, 340, "self.resize(520, 340)"),  # GenerateAnnualPatenteObligationDialog
    ("modules.taxation.ui.tax.compliance.dialogs.9",  520, 320, None),                     # GenerateMonthlyTSRObligationsDialog (same as 0)
    ("modules.taxation.ui.tax.compliance.dialogs.10", 560, 380, "self.resize(560, 380)"),  # RecordCustomsDutyObligationDialog
    ("modules.taxation.ui.tax.compliance.dialogs.11", 560, 280, "self.resize(560, 280)"),  # ExportTaxReturnPDFDialog
]

# 1. Add tokens to layout_constraints.py
layout_content = LAYOUT.read_text(encoding="utf-8")
token_lines = "\n".join(
    f'    "{key}": WindowSizeToken("{key}", {w}, {h}),'
    for key, w, h, _ in NEW_TOKENS
)
layout_content = layout_content.replace(
    '    "app.shell.menu.bar.keyboard.shortcuts.0": WindowSizeToken("app.shell.menu.bar.keyboard.shortcuts.0", 420, 380),\n}',
    f'    "app.shell.menu.bar.keyboard.shortcuts.0": WindowSizeToken("app.shell.menu.bar.keyboard.shortcuts.0", 420, 380),\n{token_lines}\n}}',
)
LAYOUT.write_text(layout_content, encoding="utf-8")
print("Updated layout_constraints.py")

# 2. Update tax_compliance_dialogs.py
dialogs_content = DIALOGS.read_text(encoding="utf-8")

# Add import if not present
if "from seeker_accounting.shared.ui.layout_constraints import apply_window_size" not in dialogs_content:
    dialogs_content = dialogs_content.replace(
        "from seeker_accounting.shared.ui.dialogs import BaseDialog",
        "from seeker_accounting.shared.ui.dialogs import BaseDialog\nfrom seeker_accounting.shared.ui.layout_constraints import apply_window_size",
    )

# Map each class to its token by reading class order
# Class names in order of appearance:
class_to_token = {
    "GenerateMonthlyVATObligationsDialog":      "modules.taxation.ui.tax.compliance.dialogs.0",
    "GenerateQuarterlyCITInstallmentsDialog":   "modules.taxation.ui.tax.compliance.dialogs.1",
    "FileTaxReturnDialog":                      "modules.taxation.ui.tax.compliance.dialogs.2",
    "FileAssessedTaxReturnDialog":              "modules.taxation.ui.tax.compliance.dialogs.3",
    "RecordTaxPaymentDialog":                   "modules.taxation.ui.tax.compliance.dialogs.4",
    "DSFExportDialog":                          "modules.taxation.ui.tax.compliance.dialogs.5",
    "SettleVATReturnDialog":                    "modules.taxation.ui.tax.compliance.dialogs.6",
    "GenerateMonthlyWithholdingObligationsDialog": "modules.taxation.ui.tax.compliance.dialogs.7",
    "GenerateAnnualPatenteObligationDialog":    "modules.taxation.ui.tax.compliance.dialogs.8",
    "GenerateMonthlyTSRObligationsDialog":      "modules.taxation.ui.tax.compliance.dialogs.9",
    "RecordCustomsDutyObligationDialog":        "modules.taxation.ui.tax.compliance.dialogs.10",
    "ExportTaxReturnPDFDialog":                 "modules.taxation.ui.tax.compliance.dialogs.11",
}

# Replace each resize call — we process the file class by class
resize_pattern = re.compile(r'\.resize\(\s*(\d+)\s*,\s*(\d+)\s*\)')

lines = dialogs_content.split("\n")
current_class = None
result_lines = []
for line in lines:
    # Detect class declaration
    class_match = re.match(r'^class (\w+)\(', line)
    if class_match:
        current_class = class_match.group(1)

    # Replace resize literal if in a known class
    if current_class in class_to_token and resize_pattern.search(line):
        token = class_to_token[current_class]
        indent = len(line) - len(line.lstrip())
        line = " " * indent + f'apply_window_size(self, "{token}")'

    result_lines.append(line)

new_dialogs = "\n".join(result_lines)
DIALOGS.write_text(new_dialogs, encoding="utf-8")
print("Updated tax_compliance_dialogs.py")
