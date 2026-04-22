from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

os.environ["QT_QPA_PLATFORM"] = "offscreen"

workspace_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(workspace_root / "src"))

from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from scripts.shared import bootstrap_script_runtime
from seeker_accounting.app.shell.main_window import MainWindow
from seeker_accounting.app.shell.sidebar import ShellSidebar
from seeker_accounting.modules.companies.dto.company_commands import CreateCompanyCommand

def main() -> int:
    temp_root = tempfile.mkdtemp(prefix="seeker_logo_smoke_")
    os.environ["SEEKER_RUNTIME_ROOT"] = temp_root

    app = QApplication.instance() or QApplication(sys.argv)
    bootstrap = bootstrap_script_runtime(app)
    service_registry = bootstrap.service_registry

    countries = service_registry.company_service.list_available_countries()
    currencies = service_registry.company_service.list_available_currencies()
    assert countries, "Expected seeded countries"
    assert currencies, "Expected seeded currencies"

    company_name = f"Logo Smoke {uuid4().hex[:8]}"
    company = service_registry.company_service.create_company(
        CreateCompanyCommand(
            legal_name=company_name,
            display_name=company_name,
            country_code=countries[0].code,
            base_currency_code=currencies[0].code,
        )
    )
    print(f"[OK] Created company: {company.display_name}")

    logo_file = Path(temp_root) / "logo.png"
    image = QImage(24, 24, QImage.Format.Format_ARGB32)
    image.fill(QColor("#2363EA"))
    assert image.save(str(logo_file), "PNG"), "Expected test logo image to save"

    service_registry.company_logo_service.set_logo(company.id, str(logo_file))
    updated_company = service_registry.company_service.get_company(company.id)
    assert updated_company.logo_storage_path, "Expected stored logo path"
    print(f"[OK] Stored logo metadata: {updated_company.logo_storage_path}")

    active_company = service_registry.company_context_service.set_active_company(company.id)
    assert active_company.logo_storage_path == updated_company.logo_storage_path
    print("[OK] Active company context carries logo path")

    main_window = MainWindow(service_registry=service_registry)
    sidebar = main_window.findChild(ShellSidebar)
    assert sidebar is not None, "Expected sidebar in main window"
    sidebar._update_company_display(active_company.company_id, active_company.company_name)

    sidebar_logo = getattr(sidebar, "_company_logo_label")
    sidebar_name = getattr(sidebar, "_company_name_label")
    assert sidebar_name.text() == company_name
    assert sidebar_logo.pixmap() is not None and not sidebar_logo.pixmap().isNull()
    print("[OK] Sidebar renders uploaded logo and wrapped company name")

    service_registry.company_logo_service.clear_logo(company.id)
    cleared_company = service_registry.company_service.get_company(company.id)
    assert cleared_company.logo_storage_path is None
    sidebar._update_company_display(active_company.company_id, active_company.company_name)
    assert sidebar_logo.text() == "Logo"
    print("[OK] Clearing logo falls back to placeholder")

    print("ALL COMPANY LOGO SIDEBAR SMOKE TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())