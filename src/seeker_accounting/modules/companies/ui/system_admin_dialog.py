from __future__ import annotations

import json
from datetime import datetime, timezone

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.companies.dto.company_dto import CompanyListItemDTO
from seeker_accounting.modules.companies.services.system_admin_company_service import (
    SystemAdminCompanyService,
)
from seeker_accounting.platform.exceptions.app_exceptions import ValidationError


class SystemAdminDialog(QDialog):
    """System administration panel for managing companies.

    Lists ALL companies (active, deactivated, pending deletion) and exposes
    lifecycle actions for each: Deactivate, Reactivate, Schedule Deletion, Restore.

    Does NOT inherit BaseDialog.
    """

    def __init__(
        self,
        company_service: SystemAdminCompanyService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = company_service

        self.setWindowTitle("System Administration — Company Management")
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.resize(900, 560)
        self.setMinimumSize(760, 420)
        self.setModal(True)
        self._build_ui()
        self._load()

    # ── Public factory ────────────────────────────────────────────────────────

    @classmethod
    def open_for(
        cls,
        company_service: SystemAdminCompanyService,
        parent: QWidget | None = None,
    ) -> None:
        dlg = cls(company_service, parent)
        dlg.exec()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header bar ────────────────────────────────────────────────────────
        header = QWidget()
        header.setFixedHeight(54)
        header.setStyleSheet("background: #1E3A5F;")
        header_row = QHBoxLayout(header)
        header_row.setContentsMargins(20, 0, 20, 0)

        title_lbl = QLabel("⚙  Company Administration")
        title_lbl.setStyleSheet("font-size: 15px; font-weight: 600; color: #F9FAFB;")
        header_row.addWidget(title_lbl)
        header_row.addStretch()

        sub_lbl = QLabel("Manage all companies — active, deactivated, and pending deletion")
        sub_lbl.setStyleSheet("font-size: 11px; color: #93C5FD;")
        header_row.addWidget(sub_lbl)
        root.addWidget(header)

        # ── Table ─────────────────────────────────────────────────────────────
        self._table = QTableWidget()
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels([
            "Display Name", "Legal Name", "Currency", "Status",
            "Scheduled Deletion", "Actions",
        ])
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.setShowGrid(False)
        self._table.verticalHeader().setVisible(False)
        self._table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(2, 80)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(3, 110)
        hh.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(4, 150)
        hh.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(5, 240)

        self._table.setStyleSheet(
            "QTableWidget { border: none; outline: none; background: #FFFFFF; "
            "alternate-background-color: #F8FAFC; }"
            "QTableWidget::item { padding: 0 8px; border: none; color: #111827; }"
            "QHeaderView::section { background: #F1F5F9; border: none; border-bottom: 1px solid #E2E8F0; "
            "padding: 8px; font-size: 11px; font-weight: 600; color: #475569; }"
        )
        self._table.setRowHeight(0, 44)
        root.addWidget(self._table)

        # ── Footer bar ────────────────────────────────────────────────────────
        footer = QWidget()
        footer.setFixedHeight(50)
        footer.setStyleSheet(
            "background: #F8FAFC; border-top: 1px solid #E2E8F0;"
        )
        footer_row = QHBoxLayout(footer)
        footer_row.setContentsMargins(16, 0, 16, 0)

        refresh_btn = QPushButton("↻  Refresh")
        refresh_btn.setFixedHeight(32)
        refresh_btn.setStyleSheet(
            "QPushButton { background: transparent; border: 1px solid #CBD5E1; "
            "border-radius: 4px; padding: 0 12px; font-size: 12px; color: #475569; }"
            "QPushButton:hover { background: #F1F5F9; }"
        )
        refresh_btn.clicked.connect(self._load)
        footer_row.addWidget(refresh_btn)
        export_btn = QPushButton("↓  Export Backup")
        export_btn.setFixedHeight(32)
        export_btn.setStyleSheet(
            "QPushButton { background: transparent; border: 1px solid #CBD5E1; "
            "border-radius: 4px; padding: 0 12px; font-size: 12px; color: #475569; }"
            "QPushButton:hover { background: #F1F5F9; }"
        )
        export_btn.clicked.connect(self._export_backup)
        footer_row.addWidget(export_btn)

        import_btn = QPushButton("↑  Import Backup")
        import_btn.setFixedHeight(32)
        import_btn.setStyleSheet(
            "QPushButton { background: transparent; border: 1px solid #CBD5E1; "
            "border-radius: 4px; padding: 0 12px; font-size: 12px; color: #475569; }"
            "QPushButton:hover { background: #F1F5F9; }"
        )
        import_btn.clicked.connect(self._import_backup)
        footer_row.addWidget(import_btn)
        footer_row.addStretch()

        close_btn = QPushButton("Close")
        close_btn.setFixedHeight(32)
        close_btn.setStyleSheet(
            "QPushButton { background: #374151; color: #fff; border: none; "
            "border-radius: 4px; padding: 0 20px; font-size: 12px; font-weight: 600; }"
            "QPushButton:hover { background: #1F2937; }"
        )
        close_btn.clicked.connect(self.accept)
        footer_row.addWidget(close_btn)

        root.addWidget(footer)

    # ── Data loading ──────────────────────────────────────────────────────────

    def _load(self) -> None:
        companies = self._service.list_all_for_admin()
        self._table.setRowCount(len(companies))
        for row, dto in enumerate(companies):
            self._table.setRowHeight(row, 44)
            self._fill_row(row, dto)

    def _fill_row(self, row: int, dto: CompanyListItemDTO) -> None:
        status_text, status_style = self._status_chip_attrs(dto)

        self._set_cell(row, 0, dto.display_name)
        self._set_cell(row, 1, dto.legal_name)
        self._set_cell(row, 2, dto.base_currency_code, Qt.AlignmentFlag.AlignCenter)

        # Status chip
        status_chip = QLabel(status_text)
        status_chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_chip.setStyleSheet(
            f"QLabel {{ {status_style} border-radius: 10px; "
            f"padding: 2px 10px; font-size: 11px; font-weight: 600; }}"
        )
        chip_wrapper = QWidget()
        chip_layout = QHBoxLayout(chip_wrapper)
        chip_layout.setContentsMargins(8, 4, 8, 4)
        chip_layout.addWidget(status_chip)
        self._table.setCellWidget(row, 3, chip_wrapper)

        # Scheduled deletion date
        if dto.deleted_at is not None:
            from datetime import timedelta
            purge_date = dto.deleted_at + timedelta(days=30)
            days_left = (purge_date.replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)).days
            days_left = max(0, days_left)
            deletion_text = f"{purge_date.strftime('%Y-%m-%d')} ({days_left}d left)"
        else:
            deletion_text = "—"
        self._set_cell(row, 4, deletion_text, Qt.AlignmentFlag.AlignCenter)

        # Action buttons
        self._table.setCellWidget(row, 5, self._make_action_widget(dto))

    def _set_cell(
        self,
        row: int,
        col: int,
        text: str,
        alignment: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
    ) -> None:
        item = QTableWidgetItem(text)
        item.setTextAlignment(alignment | Qt.AlignmentFlag.AlignVCenter)
        self._table.setItem(row, col, item)

    @staticmethod
    def _status_chip_attrs(dto: CompanyListItemDTO) -> tuple[str, str]:
        if dto.deleted_at is not None:
            return "Pending Deletion", "background: #FEF3C7; color: #92400E;"
        if dto.is_active:
            return "Active", "background: #D1FAE5; color: #065F46;"
        return "Deactivated", "background: #F3F4F6; color: #6B7280;"

    # ── Action widgets ────────────────────────────────────────────────────────

    def _make_action_widget(self, dto: CompanyListItemDTO) -> QWidget:
        wrapper = QWidget()
        row_layout = QHBoxLayout(wrapper)
        row_layout.setContentsMargins(6, 4, 6, 4)
        row_layout.setSpacing(6)

        if dto.deleted_at is not None:
            # Pending Deletion → Restore only
            restore_btn = self._small_btn("Restore", "#0369A1", "#075985")
            restore_btn.clicked.connect(lambda: self._on_restore(dto.id, dto.display_name))
            row_layout.addWidget(restore_btn)
        elif dto.is_active:
            # Active → Deactivate | Schedule Deletion
            deact_btn = self._small_btn("Deactivate", "#6B7280", "#4B5563")
            deact_btn.clicked.connect(lambda: self._on_deactivate(dto.id, dto.display_name))
            row_layout.addWidget(deact_btn)

            sched_btn = self._small_btn("Schedule Deletion", "#DC2626", "#B91C1C")
            sched_btn.clicked.connect(lambda: self._on_schedule_deletion(dto.id, dto.display_name))
            row_layout.addWidget(sched_btn)
        else:
            # Deactivated → Reactivate | Schedule Deletion
            react_btn = self._small_btn("Reactivate", "#059669", "#047857")
            react_btn.clicked.connect(lambda: self._on_reactivate(dto.id, dto.display_name))
            row_layout.addWidget(react_btn)

            sched_btn = self._small_btn("Schedule Deletion", "#DC2626", "#B91C1C")
            sched_btn.clicked.connect(lambda: self._on_schedule_deletion(dto.id, dto.display_name))
            row_layout.addWidget(sched_btn)

        row_layout.addStretch()
        return wrapper

    @staticmethod
    def _small_btn(label: str, bg: str, hover: str) -> QPushButton:
        btn = QPushButton(label)
        btn.setFixedHeight(28)
        btn.setStyleSheet(
            f"QPushButton {{ background: {bg}; color: #fff; border: none; "
            f"border-radius: 3px; padding: 0 10px; font-size: 11px; }}"
            f"QPushButton:hover {{ background: {hover}; }}"
        )
        return btn

    # ── Action handlers ───────────────────────────────────────────────────────

    def _on_deactivate(self, company_id: int, name: str) -> None:
        reply = QMessageBox.question(
            self,
            "Deactivate Company",
            f"Are you sure you want to deactivate <b>{name}</b>?<br><br>"
            "The company will no longer be accessible to users, but all data "
            "will be preserved.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            self._service.deactivate_company(company_id)
            self._load()
        except (ValidationError, Exception) as exc:
            QMessageBox.critical(self, "Error", str(exc))

    def _on_reactivate(self, company_id: int, name: str) -> None:
        reply = QMessageBox.question(
            self,
            "Reactivate Company",
            f"Reactivate <b>{name}</b> and restore user access?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            self._service.reactivate_company(company_id)
            self._load()
        except (ValidationError, Exception) as exc:
            QMessageBox.critical(self, "Error", str(exc))

    def _on_schedule_deletion(self, company_id: int, name: str) -> None:
        # Two-step confirmation for an irreversible-looking action
        first = QMessageBox.warning(
            self,
            "Schedule Permanent Deletion",
            f"You are about to schedule <b>{name}</b> for permanent deletion.<br><br>"
            "All data will be permanently deleted after 30 days unless restored.<br><br>"
            "Do you want to continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if first != QMessageBox.StandardButton.Yes:
            return

        second = QMessageBox.critical(
            self,
            "Confirm Permanent Deletion",
            f"<b>Final confirmation:</b> Permanently delete all data for <b>{name}</b> "
            f"after 30 days?<br><br>"
            "This cannot be undone once the retention window expires.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if second != QMessageBox.StandardButton.Yes:
            return

        try:
            self._service.schedule_company_deletion(company_id)
            self._load()
        except (ValidationError, Exception) as exc:
            QMessageBox.critical(self, "Error", str(exc))

    def _on_restore(self, company_id: int, name: str) -> None:
        reply = QMessageBox.question(
            self,
            "Restore Company",
            f"Restore <b>{name}</b> from scheduled deletion?<br><br>"
            "The company will be reactivated and the deletion will be cancelled.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            self._service.restore_company_from_deletion(company_id)
            self._load()
        except (ValidationError, Exception) as exc:
            QMessageBox.critical(self, "Error", str(exc))

    # ── Import / Export ───────────────────────────────────────────────────────

    _BACKUP_FORMAT = "seeker_company_backup"
    _BACKUP_VERSION = 1

    def _export_backup(self) -> None:
        companies = self._service.list_all_for_admin()
        if not companies:
            QMessageBox.information(self, "Export", "No companies to export.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Seeker Company Backup",
            "companies_backup.seeker",
            "Seeker Backup Files (*.seeker)",
        )
        if not path:
            return

        records = []
        for dto in companies:
            if dto.deleted_at is not None:
                from datetime import timedelta
                purge_date = dto.deleted_at + timedelta(days=30)
                status = "Pending Deletion"
                scheduled_deletion = purge_date.strftime("%Y-%m-%d")
            elif dto.is_active:
                status = "Active"
                scheduled_deletion = None
            else:
                status = "Deactivated"
                scheduled_deletion = None

            records.append({
                "legal_name": dto.legal_name,
                "display_name": dto.display_name,
                "country_code": dto.country_code,
                "base_currency_code": dto.base_currency_code,
                "status": status,
                "scheduled_deletion": scheduled_deletion,
            })

        payload = {
            "format": self._BACKUP_FORMAT,
            "version": self._BACKUP_VERSION,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "companies": records,
        }

        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2, ensure_ascii=False)
        except Exception as exc:
            QMessageBox.critical(self, "Export Failed", str(exc))
            return

        QMessageBox.information(
            self, "Export Complete",
            f"Exported {len(records)} company record(s) to:\n{path}"
        )

    def _import_backup(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Seeker Company Backup",
            "",
            "Seeker Backup Files (*.seeker)",
        )
        if not path:
            return

        try:
            with open(path, encoding="utf-8") as fh:
                payload = json.load(fh)
        except Exception as exc:
            QMessageBox.critical(self, "Import Failed", f"Could not read backup file:\n{exc}")
            return

        if not isinstance(payload, dict) or payload.get("format") != self._BACKUP_FORMAT:
            QMessageBox.critical(
                self, "Invalid Backup",
                "This file is not a valid Seeker company backup file."
            )
            return

        records = payload.get("companies", [])
        if not records:
            QMessageBox.information(self, "Import", "The backup file contains no company records.")
            return

        confirm = QMessageBox.question(
            self,
            "Import Company Backup",
            f"Import {len(records)} company record(s)?\n\n"
            "Existing companies will not be modified. Only new records will be created.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        from seeker_accounting.modules.companies.dto.company_commands import CreateCompanyCommand

        created = 0
        skipped = 0
        errors: list[str] = []

        for i, record in enumerate(records, start=1):
            legal_name = (record.get("legal_name") or "").strip()
            display_name = (record.get("display_name") or "").strip()
            country_code = (record.get("country_code") or "").strip()
            base_currency_code = (record.get("base_currency_code") or "").strip()

            if not legal_name or not display_name or not country_code or not base_currency_code:
                errors.append(f"Record {i}: missing required field(s) — skipped.")
                skipped += 1
                continue

            cmd = CreateCompanyCommand(
                legal_name=legal_name,
                display_name=display_name,
                country_code=country_code,
                base_currency_code=base_currency_code,
            )
            try:
                self._service.create_company(cmd)
                created += 1
            except Exception as exc:
                errors.append(f"Record {i} ({display_name}): {exc}")
                skipped += 1

        self._load()

        summary_lines = [f"Created: {created}  |  Skipped: {skipped}"]
        if errors:
            summary_lines.append("\nIssues:")
            summary_lines.extend(f"  \u2022 {e}" for e in errors[:10])
            if len(errors) > 10:
                summary_lines.append(f"  ... and {len(errors) - 10} more.")
        QMessageBox.information(self, "Import Complete", "\n".join(summary_lines))
