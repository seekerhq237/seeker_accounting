"""Pack Rollover Wizard — P10.S3.

Three-step ``WizardShell`` dialog that guides an administrator through
applying a new statutory pack version to the active company.

Steps
-----
1. **Select Pack** — list all available packs; user picks the target.
2. **Review Changes** — preview what the rollover will create/skip.
3. **Result** — outcome summary after execution.

The wizard is launched from :class:`_StatutoryPacksTab` in
``payroll_operations_workspace.py``.  The existing inline "Preview" /
"Apply" buttons remain as a quick-access fallback.
"""
from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.payroll.dto.payroll_pack_version_dto import (
    PackRolloverPreviewDTO,
    PackRolloverResultDTO,
    PackVersionListItemDTO,
)
from seeker_accounting.modules.payroll.services.payroll_pack_version_service import (
    PayrollPackVersionService,
)
from seeker_accounting.platform.exceptions import ValidationError
from seeker_accounting.shared.ui.components.inline_issue_band import ValidationIssue
from seeker_accounting.shared.ui.components.wizard_shell import (
    WizardShell,
    WizardStepDescriptor,
)
from seeker_accounting.shared.ui.message_boxes import show_error

logger = logging.getLogger(__name__)


# ── Step descriptors ──────────────────────────────────────────────────────────

_STEPS: tuple[WizardStepDescriptor, ...] = (
    WizardStepDescriptor(
        id="select",
        title="Select Pack",
        description="Choose the statutory pack version to apply.",
    ),
    WizardStepDescriptor(
        id="review",
        title="Review Changes",
        description="Confirm what will be created before applying.",
    ),
    WizardStepDescriptor(
        id="result",
        title="Result",
        description="Outcome of the rollover operation.",
    ),
)


# ── Step widgets ──────────────────────────────────────────────────────────────

class _SelectPackWidget(QWidget):
    """Step 1 — show available pack versions; user selects one."""

    def __init__(self, versions: list[PackVersionListItemDTO], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(10)

        info = QLabel(
            "Select a statutory pack version to apply to this company. "
            "Existing components and rule sets will <b>not</b> be overwritten."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self._list = QListWidget(self)
        self._list.setObjectName("PackRolloverPackList")
        self._list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        for v in versions:
            label = f"{v.display_name}  [{v.pack_code}]"
            if v.is_current:
                label += "  ✓ current"
            item = QListWidgetItem(label, self._list)
            item.setData(Qt.ItemDataRole.UserRole, v.pack_code)
            if v.is_current:
                font = item.font()
                font.setBold(True)
                item.setFont(font)

        layout.addWidget(self._list)

    def selected_pack_code(self) -> str | None:
        item = self._list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None


class _ReviewWidget(QWidget):
    """Step 2 — show the rollover preview."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(12)

        self._title = QLabel("", self)
        self._title.setObjectName("PackRolloverReviewTitle")
        layout.addWidget(self._title)

        self._detail_frame = QFrame(self)
        self._detail_frame.setObjectName("PackRolloverDetailFrame")
        self._detail_frame.setFrameShape(QFrame.Shape.StyledPanel)
        detail_layout = QVBoxLayout(self._detail_frame)
        detail_layout.setSpacing(6)
        # Rows are created dynamically in load(); start empty.
        self._detail_layout = detail_layout
        self._rows: list[QLabel] = []
        layout.addWidget(self._detail_frame)

        self._message = QLabel("", self)
        self._message.setWordWrap(True)
        self._message.setObjectName("PackRolloverMessage")
        layout.addWidget(self._message)
        layout.addStretch(1)

    def load(self, preview: PackRolloverPreviewDTO) -> None:
        self._title.setText(
            f"Rolling over to: <b>{preview.target_display_name}</b> ({preview.target_pack_code})"
        )
        rows = [
            ("Current pack", preview.current_pack_code or "None"),
            ("Components to create", str(preview.components_to_create)),
            ("Components already present", str(preview.existing_components)),
            ("Rule sets to create", str(preview.rule_sets_to_create)),
            ("Rule sets already present", str(preview.existing_rule_sets)),
        ]
        # Rebuild dynamic rows to match the actual data length.
        for lbl in self._rows:
            self._detail_layout.removeWidget(lbl)
            lbl.deleteLater()
        self._rows = []
        for key, val in rows:
            lbl = QLabel(f"<b>{key}:</b> {val}" if key else "", self._detail_frame)
            lbl.setWordWrap(True)
            self._detail_layout.addWidget(lbl)
            self._rows.append(lbl)
        self._message.setText(preview.message)


class _ResultWidget(QWidget):
    """Step 3 — post-execution outcome."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(12)

        self._icon_label = QLabel("", self)
        self._icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._icon_label)

        self._title = QLabel("", self)
        self._title.setObjectName("PackRolloverResultTitle")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title.setWordWrap(True)
        layout.addWidget(self._title)

        self._detail = QLabel("", self)
        self._detail.setWordWrap(True)
        self._detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._detail)
        layout.addStretch(1)

    def load_success(self, result: PackRolloverResultDTO) -> None:
        self._title.setText(f"Pack <b>{result.new_pack_code}</b> applied successfully.")
        parts: list[str] = []
        if result.components_created:
            parts.append(f"{result.components_created} component(s) created")
        if result.rule_sets_created:
            parts.append(f"{result.rule_sets_created} rule set(s) created")
        if result.brackets_created:
            parts.append(f"{result.brackets_created} bracket(s) created")
        if not parts:
            parts.append("No changes were needed — all records already present.")
        self._detail.setText(" · ".join(parts))

    def load_error(self, message: str) -> None:
        self._title.setText("Rollover could not be completed.")
        self._detail.setText(message)


# ── Wizard host ───────────────────────────────────────────────────────────────

class PackRolloverWizardDialog(WizardShell):
    """Three-step rollover wizard dialog.

    Usage::

        dlg = PackRolloverWizardDialog(company_id, service, parent=self)
        dlg.exec()
    """

    def __init__(
        self,
        company_id: int,
        service: PayrollPackVersionService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            title="Statutory pack rollover",
            steps=_STEPS,
            parent=parent,
            primary_label="Next",
            finish_label="Close",
            min_width=640,
            min_height=480,
        )
        self._company_id = company_id
        self._service = service

        self._selected_pack_code: str | None = None
        self._preview: PackRolloverPreviewDTO | None = None
        self._executed = False

        # Build step widgets up-front (data loaded on demand).
        try:
            versions = self._service.list_available_versions(company_id)
        except Exception:
            logger.warning("PackRolloverWizard: could not load versions", exc_info=True)
            versions = []

        self._select_widget = _SelectPackWidget(versions, self)
        self._review_widget = _ReviewWidget(self)
        self._result_widget = _ResultWidget(self)

        self.set_step_widget("select", self._select_widget)
        self.set_step_widget("review", self._review_widget)
        self.set_step_widget("result", self._result_widget)

        # Wire wizard lifecycle signals.
        self.next_requested.connect(self._on_next)
        self.back_requested.connect(self._on_back_step)
        self.finish_requested.connect(self.accept)
        self.cancel_requested.connect(self._on_cancel_requested)

    # ── Lifecycle handlers ────────────────────────────────────────────────────

    def _on_next(self, step_id: str) -> None:
        if step_id == "select":
            self._handle_select_next()
        elif step_id == "review":
            self._handle_review_next()

    def _handle_select_next(self) -> None:
        pack_code = self._select_widget.selected_pack_code()
        if pack_code is None:
            self.set_step_issues("select", [ValidationIssue(severity="error", message="Select a pack version to continue.")])
            return
        self.set_step_issues("select", [])
        self._selected_pack_code = pack_code

        # Load preview before advancing.
        try:
            self._preview = self._service.preview_rollover(self._company_id, pack_code)
        except ValidationError as exc:
            self.set_step_issues("select", [ValidationIssue(severity="error", message=str(exc))])
            return
        except Exception:
            logger.warning("PackRolloverWizard: preview_rollover failed", exc_info=True)
            self.set_step_issues("select", [ValidationIssue(severity="error", message="Failed to load preview. Check the application log.")])
            return

        self._review_widget.load(self._preview)
        self.set_step_status("select", "complete")
        self.advance_step()

    def _handle_review_next(self) -> None:
        """Execute the rollover and advance to the result step."""
        if not self._selected_pack_code:
            self.go_back()
            return
        # Guard: do not allow re-execution if the rollover already ran.
        if self._executed:
            self.advance_step()
            return
        try:
            result = self._service.execute_rollover(self._company_id, self._selected_pack_code)
        except ValidationError as exc:
            self.set_step_issues("review", [ValidationIssue(severity="error", message=str(exc))])
            return
        except Exception:
            logger.warning("PackRolloverWizard: execute_rollover failed", exc_info=True)
            self._result_widget.load_error("An unexpected error occurred. Check the application log.")
            self.set_step_status("review", "issues")
            self.advance_step()
            return

        self._executed = True
        self._result_widget.load_success(result)
        self.set_step_status("review", "complete")
        self.advance_step()

    def _on_back_step(self, step_id: str) -> None:
        self.go_back()

    def _on_cancel_requested(self) -> None:
        self.reject()

    @property
    def was_applied(self) -> bool:
        """True if the wizard completed an actual rollover execution."""
        return self._executed
