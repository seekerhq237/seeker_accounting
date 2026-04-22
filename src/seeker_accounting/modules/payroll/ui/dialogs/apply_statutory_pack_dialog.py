from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.modules.payroll.dto.payroll_statutory_pack_dto import ApplyPackResultDTO
from seeker_accounting.platform.exceptions import NotFoundError, ValidationError


class ApplyStatutoryPackDialog(QDialog):
    """Dialog for selecting and applying a statutory payroll pack to a company.

    Shows available packs, the currently applied pack version (if any), a
    confirmation note, and an inline result summary after application.
    Re-applying is safe — existing records are never overwritten.
    """

    def __init__(
        self,
        service_registry: ServiceRegistry,
        company_id: int,
        company_name: str,
        current_pack_version: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._sr = service_registry
        self._company_id = company_id
        self._result: ApplyPackResultDTO | None = None

        self.setWindowTitle(f"Apply Statutory Pack — {company_name}")
        self.setModal(True)
        self.resize(520, 420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # ── Pack selection card ───────────────────────────────────────────────
        sel_card = QFrame(self)
        sel_card.setObjectName("PageCard")
        sel_layout = QVBoxLayout(sel_card)
        sel_layout.setContentsMargins(18, 16, 18, 16)
        sel_layout.setSpacing(10)

        sel_hdr = QLabel("Select Statutory Pack", sel_card)
        sel_hdr.setObjectName("CardTitle")
        sel_layout.addWidget(sel_hdr)

        # Current pack row
        if current_pack_version:
            cur_row = QWidget(sel_card)
            cur_rl = QHBoxLayout(cur_row)
            cur_rl.setContentsMargins(0, 0, 0, 0)
            cur_rl.setSpacing(8)
            cur_lbl = QLabel("Currently applied:", cur_row)
            cur_lbl.setProperty("role", "caption")
            cur_rl.addWidget(cur_lbl)
            cur_val = QLabel(current_pack_version, cur_row)
            cur_val.setObjectName("ToolbarValue")
            cur_rl.addWidget(cur_val, 1)
            sel_layout.addWidget(cur_row)

        # Pack combo
        pack_row = QWidget(sel_card)
        pack_rl = QHBoxLayout(pack_row)
        pack_rl.setContentsMargins(0, 0, 0, 0)
        pack_rl.setSpacing(8)
        pack_lbl = QLabel("Pack to apply:", pack_row)
        pack_lbl.setProperty("role", "caption")
        pack_lbl.setFixedWidth(120)
        pack_rl.addWidget(pack_lbl)
        self._pack_combo = QComboBox(pack_row)
        try:
            packs = self._sr.payroll_statutory_pack_service.list_available_packs()
        except Exception:
            packs = []
        for p in packs:
            self._pack_combo.addItem(f"{p.display_name} ({p.pack_code})", p.pack_code)
        pack_rl.addWidget(self._pack_combo, 1)
        sel_layout.addWidget(pack_row)

        layout.addWidget(sel_card)

        # ── Pack description card ─────────────────────────────────────────────
        info_card = QFrame(self)
        info_card.setObjectName("PageCard")
        info_layout = QVBoxLayout(info_card)
        info_layout.setContentsMargins(18, 16, 18, 16)
        info_layout.setSpacing(8)

        info_hdr = QLabel("About This Pack", info_card)
        info_hdr.setObjectName("CardTitle")
        info_layout.addWidget(info_hdr)

        self._desc_label = QLabel(info_card)
        self._desc_label.setObjectName("PageSummary")
        self._desc_label.setWordWrap(True)
        self._desc_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        info_layout.addWidget(self._desc_label)

        idempotent_note = QLabel(
            "Re-applying is safe: existing components and rule sets are never overwritten. "
            "Only missing records are created.",
            info_card,
        )
        idempotent_note.setObjectName("PageSummary")
        idempotent_note.setWordWrap(True)
        info_layout.addWidget(idempotent_note)

        layout.addWidget(info_card)

        # ── Result area ───────────────────────────────────────────────────────
        self._result_card = QFrame(self)
        self._result_card.setObjectName("PageCard")
        result_layout = QVBoxLayout(self._result_card)
        result_layout.setContentsMargins(18, 16, 18, 16)
        result_layout.setSpacing(8)

        result_hdr = QLabel("Result", self._result_card)
        result_hdr.setObjectName("CardTitle")
        result_layout.addWidget(result_hdr)

        self._result_label = QLabel(self._result_card)
        self._result_label.setWordWrap(True)
        self._result_label.setObjectName("PageSummary")
        result_layout.addWidget(self._result_label)

        self._result_card.hide()
        layout.addWidget(self._result_card)

        # ── Error label ───────────────────────────────────────────────────────
        self._error_label = QLabel(self)
        self._error_label.setObjectName("FormError")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        layout.addWidget(self._error_label)

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_row = QWidget(self)
        btn_rl = QHBoxLayout(btn_row)
        btn_rl.setContentsMargins(0, 0, 0, 0)
        btn_rl.setSpacing(8)

        self._apply_btn = QPushButton("Apply Pack", btn_row)
        self._apply_btn.setProperty("variant", "primary")
        self._apply_btn.clicked.connect(self._on_apply)
        btn_rl.addWidget(self._apply_btn)

        self._close_btn = QPushButton("Close", btn_row)
        self._close_btn.clicked.connect(self.accept)
        btn_rl.addWidget(self._close_btn)
        btn_rl.addStretch()

        layout.addWidget(btn_row)

        self._update_description()
        self._pack_combo.currentIndexChanged.connect(self._update_description)

        from seeker_accounting.shared.ui.help_button import install_help_button
        install_help_button(self, "dialog.apply_statutory_pack", dialog=True)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _update_description(self) -> None:
        pack_code = self._pack_combo.currentData()
        if pack_code is None:
            self._desc_label.setText("")
            return
        try:
            packs = self._sr.payroll_statutory_pack_service.list_available_packs()
        except Exception:
            packs = []
        for p in packs:
            if p.pack_code == pack_code:
                self._desc_label.setText(p.description)
                return
        self._desc_label.setText("")

    def _on_apply(self) -> None:
        self._error_label.hide()
        self._result_card.hide()

        pack_code = self._pack_combo.currentData()
        if not pack_code:
            self._error_label.setText("Select a pack to apply.")
            self._error_label.show()
            return

        self._apply_btn.setEnabled(False)
        try:
            result = self._sr.payroll_statutory_pack_service.apply_pack(
                self._company_id, pack_code
            )
        except (ValidationError, NotFoundError) as exc:
            self._error_label.setText(str(exc))
            self._error_label.show()
            self._apply_btn.setEnabled(True)
            return
        except Exception as exc:
            self._error_label.setText(f"Unexpected error: {exc}")
            self._error_label.show()
            self._apply_btn.setEnabled(True)
            return

        self._result = result
        summary = (
            f"Components: {result.components_created} created, "
            f"{result.components_skipped} already present.\n"
            f"Rule sets: {result.rule_sets_created} created, "
            f"{result.rule_sets_skipped} already present.\n"
            f"Brackets: {result.brackets_created} created.\n"
            + ("Settings updated: pack version recorded." if result.settings_updated else "")
        )
        self._result_label.setText(summary.strip())
        self._result_card.show()
        self._apply_btn.setText("Re-apply Pack")
        self._apply_btn.setEnabled(True)

    @property
    def applied_result(self) -> ApplyPackResultDTO | None:
        """Non-None if a pack was successfully applied during this dialog session."""
        return self._result
