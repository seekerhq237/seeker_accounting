"""Fix misplaced import logging — move it to after from __future__ import annotations."""
from __future__ import annotations
import re
from pathlib import Path

ROOT = Path("src/seeker_accounting/modules")

fixed = []
for py_file in sorted(ROOT.rglob("*.py")):
    if "__pycache__" in py_file.parts:
        continue
    content = py_file.read_text(encoding="utf-8")

    # Check for the broken pattern: starts with "import logging\n" but also has
    # "from __future__ import annotations" later in the file (not already first)
    if not content.startswith("import logging\n"):
        continue
    if "from __future__ import annotations" not in content:
        continue

    # Broken: import logging is first, but future import is somewhere below.
    # Fix: remove the leading "import logging\n" and insert after future import line.
    content_without_leading = content[len("import logging\n"):]

    if "from __future__ import annotations\n" in content_without_leading:
        fixed_content = content_without_leading.replace(
            "from __future__ import annotations\n",
            "from __future__ import annotations\nimport logging\n",
            1,
        )
    else:
        # Future import is on a line without trailing newline (edge case)
        fixed_content = content_without_leading

    py_file.write_text(fixed_content, encoding="utf-8")
    fixed.append(str(py_file.relative_to(ROOT)))

print(f"Repaired {len(fixed)} files:")
for f in fixed:
    print(f"  {f}")
