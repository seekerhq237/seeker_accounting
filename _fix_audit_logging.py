"""One-shot script: replace silent audit-trail excepts with warning logs."""
from __future__ import annotations
from pathlib import Path

ROOT = Path(__file__).parent / "src" / "seeker_accounting" / "modules"

OLD_A = (
    "        except Exception:\n"
    "            pass  # Audit must not break business operations\n"
)
NEW_A = (
    "        except Exception:\n"
    '            logging.getLogger(__name__).warning("Audit event failed", exc_info=True)\n'
)

# Less-common 12-space indent variant (nested blocks)
OLD_B = (
    "            except Exception:\n"
    "                pass  # Audit must not break business operations\n"
)
NEW_B = (
    "            except Exception:\n"
    '                logging.getLogger(__name__).warning("Audit event failed", exc_info=True)\n'
)

changed: list[str] = []

for py_file in sorted(ROOT.rglob("*.py")):
    # UI files: their silent excepts are intentional defensive guards, leave them.
    if "ui" in py_file.parts:
        continue

    content = py_file.read_text(encoding="utf-8")

    if OLD_A not in content and OLD_B not in content:
        continue

    new_content = content.replace(OLD_A, NEW_A).replace(OLD_B, NEW_B)

    # Ensure import logging is present
    if "import logging" not in new_content:
        if new_content.startswith("from __future__ import annotations\n"):
            new_content = new_content.replace(
                "from __future__ import annotations\n",
                "from __future__ import annotations\nimport logging\n",
                1,
            )
        else:
            new_content = "import logging\n" + new_content

    py_file.write_text(new_content, encoding="utf-8")
    changed.append(str(py_file.relative_to(ROOT)))

print(f"Fixed {len(changed)} files:")
for f in changed:
    print(f"  {f}")
