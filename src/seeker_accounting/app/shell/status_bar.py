"""Shell status bar - compact bottom strip showing company/period/user context."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget

from seeker_accounting import __version__
from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.shared.ui.styles.tokens import DEFAULT_TOKENS
from seeker_accounting.shared.utils.text import coalesce_text


class ShellStatusBar(QFrame):
    """Thin status rail rendered at the bottom of the shell content area."""

    def __init__(self, service_registry: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._sr = service_registry
        self._db_backend = "SQLite"

        self.setObjectName("StatusRail")
        self.setFixedHeight(DEFAULT_TOKENS.sizes.status_rail_height)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(8)

        self._context_label = QLabel(self)
        self._context_label.setObjectName("StatusRailText")
        layout.addWidget(self._context_label, 0, Qt.AlignmentFlag.AlignVCenter)

        layout.addStretch(1)

        self._task_label = QLabel("Ready", self)
        self._task_label.setObjectName("StatusRailText")
        self._task_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._task_label, 0, Qt.AlignmentFlag.AlignVCenter)

        layout.addStretch(1)

        self._meta_label = QLabel(self)
        self._meta_label.setObjectName("StatusRailText")
        layout.addWidget(self._meta_label, 0, Qt.AlignmentFlag.AlignVCenter)

        service_registry.active_company_context.active_company_changed.connect(
            lambda *_: self._refresh()
        )
        self._refresh()

    def set_db_backend(self, backend: str) -> None:
        """Override the right-side backend label (e.g. 'PostgreSQL')."""
        self._db_backend = backend
        self._meta_label.setText(f"{self._db_backend}  ·  v{__version__}")

    def refresh(self) -> None:
        self._refresh()

    def _refresh(self) -> None:
        ctx = self._sr.active_company_context
        acc = self._sr.app_context

        company = coalesce_text(ctx.company_name, "No company")
        user = coalesce_text(acc.current_user_display_name, "Guest")

        period_text = "-"
        company_id = ctx.company_id
        if isinstance(company_id, int) and company_id > 0:
            try:
                period = self._sr.fiscal_calendar_service.get_current_period(company_id)
                if period:
                    period_text = period.period_code
            except Exception:
                pass

        self._context_label.setText("  ·  ".join((company, period_text, user)))
        self._meta_label.setText(f"{self._db_backend}  ·  v{__version__}")
