"""Fix remaining audit-trail silent excepts that lack the standard comment."""
from __future__ import annotations
from pathlib import Path

BASE = Path(__file__).parent / "src" / "seeker_accounting" / "modules"

# 8-space indent: audit _record_audit methods with bare pass (no comment)
OLD_BARE = (
    "        except Exception:\n"
    "            pass\n"
)
NEW_BARE = (
    "        except Exception:\n"
    '            logging.getLogger(__name__).warning("Audit event failed", exc_info=True)\n'
)

# pragma: no cover variant
OLD_PRAGMA = (
    "        except Exception:  # pragma: no cover - audit must not break business ops\n"
    "            pass\n"
)
NEW_PRAGMA = (
    "        except Exception:  # pragma: no cover\n"
    '            logging.getLogger(__name__).warning("Audit event failed", exc_info=True)\n'
)

TARGET_FILES = [
    BASE / "inventory" / "services" / "bill_of_material_service.py",
    BASE / "inventory" / "services" / "stock_count_service.py",
    BASE / "inventory" / "services" / "production_order_service.py",
    BASE / "inventory" / "services" / "item_variant_service.py",
    BASE / "inventory" / "services" / "item_traceability_service.py",
    BASE / "inventory" / "services" / "inventory_reference_data_service.py",
    BASE / "purchases" / "services" / "purchase_credit_note_service.py",
    BASE / "purchases" / "services" / "purchase_credit_note_posting_service.py",
    BASE / "sales" / "services" / "sales_credit_note_service.py",
    BASE / "sales" / "services" / "sales_credit_note_posting_service.py",
]

changed: list[str] = []

for py_file in TARGET_FILES:
    if not py_file.exists():
        print(f"  SKIP (not found): {py_file.name}")
        continue

    content = py_file.read_text(encoding="utf-8")
    new_content = content

    new_content = new_content.replace(OLD_BARE, NEW_BARE)
    new_content = new_content.replace(OLD_PRAGMA, NEW_PRAGMA)

    if new_content == content:
        print(f"  NO MATCH: {py_file.name}")
        continue

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
    changed.append(py_file.name)

print(f"\nFixed {len(changed)} files:")
for f in changed:
    print(f"  {f}")
