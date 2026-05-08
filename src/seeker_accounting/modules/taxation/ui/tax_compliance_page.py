"""Tax Compliance workspace page.

A single page that surfaces the obligations / returns / payments
backends (T4) and the DSF export service (T5). Three tables are stacked
vertically with a single action toolbar and a footer for the DSF action.

Architecture: this page is a UI surface only. Every state transition
(generate, draft, file, record, export) goes through a service via the
service registry. The page never builds journal entries or persistence
itself.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal

from PySide6.QtCore import Qt, QSortFilterProxyModel
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QPushButton,
    QStackedWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.app.dependency.service_registry import ServiceRegistry
from seeker_accounting.app.shell.ribbon import RibbonHostMixin
from seeker_accounting.modules.taxation.constants import (
    ALL_ASSESSED_RETURN_TAX_TYPES,
    OBLIGATION_STATUS_OPEN,
    RETURN_STATUS_DRAFT,
    RETURN_STATUS_FILED,
    TAX_TYPE_VAT,
)
from seeker_accounting.modules.taxation.dto.tax_compliance_dto import (
    DraftVATReturnCommand,
    TaxObligationDTO,
    TaxPaymentDTO,
    TaxReturnDTO,
)
from seeker_accounting.modules.taxation.ui.tax_compliance_dialogs import (
    DSFExportDialog,
    ExportTaxReturnPDFDialog,
    FileAssessedTaxReturnDialog,
    FileTaxReturnDialog,
    GenerateAnnualPatenteObligationDialog,
    GenerateMonthlyTSRObligationsDialog,
    GenerateMonthlyVATObligationsDialog,
    GenerateMonthlyWithholdingObligationsDialog,
    GenerateQuarterlyCITInstallmentsDialog,
    RecordCustomsDutyObligationDialog,
    RecordTaxPaymentDialog,
    SettleVATReturnDialog,
)
from seeker_accounting.platform.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from seeker_accounting.shared.ui.background_task import run_with_progress
from seeker_accounting.shared.ui.components.read_only_table_model import (
    ReadOnlyTableModel,
    selected_user_data,
)
from seeker_accounting.shared.ui.message_boxes import (
    show_error,
    show_info,
)
from seeker_accounting.shared.ui.table_helpers import configure_compact_table


_log = logging.getLogger(__name__)

_DASH = "\u2014"


def _load_obligations(service_registry: object, company_id: int) -> list:
    """Load tax obligations; swallow PermissionDeniedError."""
    try:
        return list(service_registry.tax_obligation_service.list_obligations(company_id))
    except PermissionDeniedError:
        return []


def _load_returns(service_registry: object, company_id: int) -> list:
    """Load tax returns; swallow PermissionDeniedError."""
    try:
        return list(service_registry.tax_return_service.list_returns(company_id))
    except PermissionDeniedError:
        return []


def _money(value: Decimal | float | int | None) -> str:
    if value is None:
        return _DASH
    return f"{Decimal(value):,.2f}"


def _date_text(value: date | None) -> str:
    if value is None:
        return _DASH
    return value.isoformat()




class TaxCompliancePage(RibbonHostMixin, QWidget):
    OBLIGATION_COLUMNS: tuple[str, ...] = (
        "Type",
        "Period start",
        "Period end",
        "Due date",
        "Status",
        "Notes",
    )
    RETURN_COLUMNS: tuple[str, ...] = (
        "Type",
        "Period start",
        "Period end",
        "Status",
        "Total due",
        "Total paid",
        "Filed at",
        "OTP / external ref",
    )
    PAYMENT_COLUMNS: tuple[str, ...] = (
        "Date",
        "Amount",
        "Method",
        "Reference",
        "Return id",
    )

    def __init__(
        self,
        service_registry: ServiceRegistry,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_registry = service_registry
        self._obligations: list[TaxObligationDTO] = []
        self._returns: list[TaxReturnDTO] = []
        self._payments: list[TaxPaymentDTO] = []

        self.setObjectName("TaxCompliancePage")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_action_bar())

        self._stack = QStackedWidget(self)
        self._no_company_card = self._build_no_company_card()
        self._workspace = self._build_workspace()
        self._stack.addWidget(self._no_company_card)
        self._stack.addWidget(self._workspace)
        root.addWidget(self._stack, 1)

        self._service_registry.active_company_context.active_company_changed.connect(
            lambda *_: self.reload()
        )
        self.reload()

    # ── Action bar ────────────────────────────────────────────────────

    def _build_action_bar(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageToolbar")

        layout = QHBoxLayout(card)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(6)

        title = QLabel("Tax Compliance", card)
        title.setObjectName("ToolbarTitle")
        layout.addWidget(title)

        self._meta_label = QLabel(card)
        self._meta_label.setObjectName("ToolbarMeta")
        layout.addWidget(self._meta_label)

        layout.addStretch(1)

        self._generate_button = QPushButton("Generate VAT Calendar", card)
        self._generate_button.setProperty("variant", "primary")
        self._generate_button.clicked.connect(self._handle_generate_obligations)
        layout.addWidget(self._generate_button)

        self._cit_button = QPushButton("Generate CIT Installments", card)
        self._cit_button.setProperty("variant", "secondary")
        self._cit_button.clicked.connect(self._handle_generate_cit_installments)
        layout.addWidget(self._cit_button)

        self._more_generators_button = QPushButton("More Generators \u25BE", card)
        self._more_generators_button.setProperty("variant", "secondary")
        self._more_generators_menu = QMenu(self._more_generators_button)
        self._wht_action = QAction("Generate Withholding Calendar\u2026", self)
        self._wht_action.triggered.connect(self._handle_generate_withholding)
        self._more_generators_menu.addAction(self._wht_action)
        self._patente_action = QAction("Generate Patente Obligation\u2026", self)
        self._patente_action.triggered.connect(self._handle_generate_patente)
        self._more_generators_menu.addAction(self._patente_action)
        self._tsr_action = QAction("Generate TSR Calendar\u2026", self)
        self._tsr_action.triggered.connect(self._handle_generate_tsr)
        self._more_generators_menu.addAction(self._tsr_action)
        self._more_generators_menu.addSeparator()
        self._customs_action = QAction("Record Customs Duty\u2026", self)
        self._customs_action.triggered.connect(self._handle_record_customs)
        self._more_generators_menu.addAction(self._customs_action)
        self._more_generators_button.setMenu(self._more_generators_menu)
        layout.addWidget(self._more_generators_button)

        self._draft_button = QPushButton("Draft VAT Return", card)
        self._draft_button.setProperty("variant", "secondary")
        self._draft_button.clicked.connect(self._handle_draft_return)
        layout.addWidget(self._draft_button)

        self._file_button = QPushButton("File Return", card)
        self._file_button.setProperty("variant", "secondary")
        self._file_button.clicked.connect(self._handle_file_return)
        layout.addWidget(self._file_button)

        self._settle_button = QPushButton("Settle Return", card)
        self._settle_button.setProperty("variant", "secondary")
        self._settle_button.clicked.connect(self._handle_settle_return)
        layout.addWidget(self._settle_button)

        self._payment_button = QPushButton("Record Payment", card)
        self._payment_button.setProperty("variant", "secondary")
        self._payment_button.clicked.connect(self._handle_record_payment)
        layout.addWidget(self._payment_button)

        self._export_pdf_button = QPushButton("Export PDF", card)
        self._export_pdf_button.setProperty("variant", "secondary")
        self._export_pdf_button.clicked.connect(self._handle_export_pdf)
        layout.addWidget(self._export_pdf_button)

        self._dsf_button = QPushButton("Export DSF", card)
        self._dsf_button.setProperty("variant", "secondary")
        self._dsf_button.clicked.connect(self._handle_export_dsf)
        layout.addWidget(self._dsf_button)

        self._refresh_button = QPushButton("Refresh", card)
        self._refresh_button.setProperty("variant", "ghost")
        self._refresh_button.clicked.connect(self.reload)
        layout.addWidget(self._refresh_button)

        return card

    # ── No-company state ──────────────────────────────────────────────

    def _build_no_company_card(self) -> QWidget:
        card = QFrame(self)
        card.setObjectName("PageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(10)

        title = QLabel("No active company", card)
        title.setObjectName("EmptyStateTitle")
        layout.addWidget(title)

        body = QLabel(
            "Select a company from the top context bar to manage tax "
            "obligations, returns, payments, and the DSF export.",
            card,
        )
        body.setWordWrap(True)
        layout.addWidget(body)
        layout.addStretch(1)

        return card

    # ── Workspace ─────────────────────────────────────────────────────

    def _build_workspace(self) -> QWidget:
        wrapper = QFrame(self)
        wrapper.setObjectName("PageCard")

        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)

        self._obligations_table, self._obligations_model, self._obligations_proxy = self._build_section(
            layout,
            heading="Obligations",
            description=(
                "Generated tax obligations (one per filing period). Use the "
                "calendar to populate annual VAT obligations idempotently."
            ),
            columns=self.OBLIGATION_COLUMNS,
        )

        self._returns_table, self._returns_model, self._returns_proxy = self._build_section(
            layout,
            heading="Returns",
            description=(
                "Drafted and filed tax returns. Drafts can be redrawn from "
                "posted invoices; filed returns are immutable."
            ),
            columns=self.RETURN_COLUMNS,
            right_align_cols=frozenset({4, 5}),
        )

        self._payments_table, self._payments_model, self._payments_proxy = self._build_section(
            layout,
            heading="Payments (selected return)",
            description=(
                "Payments are recorded against returns. Select a return above "
                "to view its payments."
            ),
            columns=self.PAYMENT_COLUMNS,
            right_align_cols=frozenset({1}),
        )

        layout.addStretch(1)

        self._obligations_table.selectionModel().selectionChanged.connect(
            self._update_action_state
        )
        self._returns_table.selectionModel().selectionChanged.connect(self._handle_return_selected)

        return wrapper

    def _build_section(
        self,
        parent_layout: QVBoxLayout,
        *,
        heading: str,
        description: str,
        columns: tuple[str, ...],
        right_align_cols: frozenset[int] | None = None,
    ) -> tuple[QTableView, ReadOnlyTableModel, QSortFilterProxyModel]:
        section = QFrame(self)
        section.setObjectName("DialogSection")

        v = QVBoxLayout(section)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)

        heading_label = QLabel(heading, section)
        heading_label.setObjectName("DialogSectionTitle")
        v.addWidget(heading_label)

        desc_label = QLabel(description, section)
        desc_label.setObjectName("DialogSectionSummary")
        desc_label.setWordWrap(True)
        v.addWidget(desc_label)

        model = ReadOnlyTableModel(list(columns), right_align_cols)
        proxy = QSortFilterProxyModel(section)
        proxy.setSourceModel(model)
        table = QTableView(section)
        configure_compact_table(table)
        table.setModel(proxy)
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setMinimumHeight(160)
        v.addWidget(table)

        parent_layout.addWidget(section)
        return table, model, proxy

    # ── Reload ────────────────────────────────────────────────────────

    def reload(self) -> None:
        active = self._active_company()
        if active is None:
            self._obligations = []
            self._returns = []
            self._payments = []
            self._meta_label.setText("Select a company")
            self._set_actions_enabled(False, False, False, False, False, False, False, False, False)
            self._stack.setCurrentWidget(self._no_company_card)
            return

        company_id = active.company_id
        task = run_with_progress(
            parent=self,
            title="Tax Compliance",
            message="Loading tax data…",
            worker=lambda: (
                _load_obligations(self._service_registry, company_id),
                _load_returns(self._service_registry, company_id),
            ),
        )
        if task.cancelled:
            return
        if task.error is not None:
            _log.warning("Failed to load tax compliance data: %s", task.error)
            show_error(self, "Tax Compliance", f"Could not load tax data.\n\n{task.error}")
            return

        obligations, returns = task.value
        self._obligations = obligations
        self._returns = returns
        self._payments = []  # populated on return selection
        self._populate_obligations()
        self._populate_returns()
        self._populate_payments()
        self._meta_label.setText(
            f"{len(self._obligations)} obligation(s) \u00b7 {len(self._returns)} return(s)"
        )
        self._update_action_state()
        self._stack.setCurrentWidget(self._workspace)

    # ── Populate tables ───────────────────────────────────────────────

    def _populate_obligations(self) -> None:
        data = [
            [ob.tax_type_code, _date_text(ob.period_start), _date_text(ob.period_end),
             _date_text(ob.due_date), ob.status_code, ob.notes or ""]
            for ob in self._obligations
        ]
        self._obligations_model.reset_data(data, self._obligations)

    def _populate_returns(self) -> None:
        data = [
            [
                r.tax_type_code,
                _date_text(r.period_start),
                _date_text(r.period_end),
                r.status_code,
                _money(r.total_due_amount),
                _money(r.total_paid_amount),
                r.filed_at.isoformat() if r.filed_at else _DASH,
                r.otp_reference or r.external_reference or "",
            ]
            for r in self._returns
        ]
        self._returns_model.reset_data(data, self._returns)

    def _populate_payments(self) -> None:
        data = [
            [
                _date_text(p.payment_date),
                _money(p.amount),
                p.payment_method_code,
                p.reference or "",
                str(p.tax_return_id) if p.tax_return_id else "",
            ]
            for p in self._payments
        ]
        self._payments_model.reset_data(data, self._payments)

    # ── Selection / state ─────────────────────────────────────────────

    def _selected_obligation(self) -> TaxObligationDTO | None:
        return selected_user_data(self._obligations_table)

    def _selected_return(self) -> TaxReturnDTO | None:
        return selected_user_data(self._returns_table)

    def _set_actions_enabled(
        self,
        generate: bool,
        cit: bool,
        more_generators: bool,
        draft: bool,
        file_return: bool,
        settle: bool,
        record_payment: bool,
        export_pdf: bool,
        dsf: bool,
    ) -> None:
        self._generate_button.setEnabled(generate)
        self._cit_button.setEnabled(cit)
        self._more_generators_button.setEnabled(more_generators)
        self._draft_button.setEnabled(draft)
        self._file_button.setEnabled(file_return)
        self._settle_button.setEnabled(settle)
        self._payment_button.setEnabled(record_payment)
        self._export_pdf_button.setEnabled(export_pdf)
        self._dsf_button.setEnabled(dsf)

    def _update_action_state(self) -> None:
        active = self._active_company()
        if active is None:
            self._set_actions_enabled(
                False, False, False, False, False, False, False, False, False
            )
            self._notify_ribbon_state_changed()
            return

        perm = self._service_registry.permission_service
        ob = self._selected_obligation()
        rt = self._selected_return()

        can_manage_obligations = perm.has_permission("taxation.obligations.manage")
        can_manage_returns = perm.has_permission("taxation.returns.manage")
        can_file_return = perm.has_permission("taxation.returns.file")
        can_settle_return = perm.has_permission("taxation.returns.settle")
        can_manage_payments = perm.has_permission("taxation.payments.manage")
        can_export_dsf = perm.has_permission("taxation.dsf.export")
        can_export_pdf = perm.has_permission("taxation.returns.export_pdf")

        # Draft is allowed on an OPEN obligation (or on existing draft to redraft).
        draft_eligible = ob is not None and ob.status_code in {OBLIGATION_STATUS_OPEN}
        # File only works on a DRAFT return.
        file_eligible = rt is not None and rt.status_code == RETURN_STATUS_DRAFT
        # Settle only works on a FILED VAT return that is not yet settled.
        settle_eligible = (
            rt is not None
            and rt.status_code == RETURN_STATUS_FILED
            and rt.tax_type_code == TAX_TYPE_VAT
            and rt.journal_entry_id is None
        )
        # Record payment only works on FILED returns (must be an actual liability).
        payment_eligible = rt is not None and rt.status_code == RETURN_STATUS_FILED
        # PDF export works on any selected return.
        export_pdf_eligible = rt is not None

        self._set_actions_enabled(
            generate=can_manage_obligations,
            cit=can_manage_obligations,
            more_generators=can_manage_obligations,
            draft=can_manage_returns and draft_eligible,
            file_return=can_file_return and file_eligible,
            settle=can_settle_return and settle_eligible,
            record_payment=can_manage_payments and payment_eligible,
            export_pdf=can_export_pdf and export_pdf_eligible,
            dsf=can_export_dsf,
        )
        self._notify_ribbon_state_changed()

    def _handle_return_selected(self) -> None:
        rt = self._selected_return()
        active = self._active_company()
        if rt is None or active is None:
            self._payments = []
            self._populate_payments()
            self._update_action_state()
            return

        try:
            self._payments = self._service_registry.tax_payment_service.list_payments_for_return(
                active.company_id, rt.id
            )
        except PermissionDeniedError:
            self._payments = []
        except Exception as exc:  # pragma: no cover - defensive
            self._payments = []
            show_error(self, "Tax Compliance", f"Could not load payments.\n\n{exc}")

        self._populate_payments()
        self._update_action_state()

    # ── Actions ───────────────────────────────────────────────────────

    def _handle_generate_obligations(self) -> None:
        active = self._active_company()
        if active is None:
            return
        dialog = GenerateMonthlyVATObligationsDialog(
            self._service_registry, active.company_id, parent=self
        )
        if dialog.exec():
            generated = dialog.generated_obligations()
            show_info(
                self,
                "VAT Calendar",
                f"{len(generated)} obligation row(s) ensured for the year.",
            )
            self.reload()

    def _handle_generate_cit_installments(self) -> None:
        active = self._active_company()
        if active is None:
            return
        dialog = GenerateQuarterlyCITInstallmentsDialog(
            self._service_registry, active.company_id, parent=self
        )
        if dialog.exec():
            generated = dialog.generated_obligations()
            show_info(
                self,
                "CIT Installments",
                f"{len(generated)} quarterly obligation row(s) ensured for the year.",
            )
            self.reload()

    def _handle_generate_withholding(self) -> None:
        active = self._active_company()
        if active is None:
            return
        dialog = GenerateMonthlyWithholdingObligationsDialog(
            self._service_registry, active.company_id, parent=self
        )
        if dialog.exec():
            generated = dialog.generated_obligations()
            show_info(
                self,
                "Withholding Calendar",
                f"{len(generated)} monthly withholding obligation row(s) ensured.",
            )
            self.reload()

    def _handle_generate_patente(self) -> None:
        active = self._active_company()
        if active is None:
            return
        dialog = GenerateAnnualPatenteObligationDialog(
            self._service_registry, active.company_id, parent=self
        )
        if dialog.exec() and dialog.generated_obligation() is not None:
            show_info(
                self,
                "Patente Obligation",
                "Annual Patente obligation ensured for the selected year.",
            )
            self.reload()

    def _handle_generate_tsr(self) -> None:
        active = self._active_company()
        if active is None:
            return
        dialog = GenerateMonthlyTSRObligationsDialog(
            self._service_registry, active.company_id, parent=self
        )
        if dialog.exec():
            generated = dialog.generated_obligations()
            show_info(
                self,
                "TSR Calendar",
                f"{len(generated)} monthly TSR obligation row(s) ensured.",
            )
            self.reload()

    def _handle_record_customs(self) -> None:
        active = self._active_company()
        if active is None:
            return
        dialog = RecordCustomsDutyObligationDialog(
            self._service_registry, active.company_id, parent=self
        )
        if dialog.exec() and dialog.generated_obligation() is not None:
            show_info(
                self,
                "Customs Duty",
                "Customs-duty obligation recorded.",
            )
            self.reload()

    # ── IRibbonHost ───────────────────────────────────────────────────

    def _ribbon_commands(self) -> dict:
        return {
            "tax_compliance.generate_vat_calendar": self._handle_generate_obligations,
            "tax_compliance.generate_cit_installments": self._handle_generate_cit_installments,
            "tax_compliance.generate_withholding_calendar": self._handle_generate_withholding,
            "tax_compliance.generate_patente_obligation": self._handle_generate_patente,
            "tax_compliance.generate_tsr_calendar": self._handle_generate_tsr,
            "tax_compliance.record_customs_duty": self._handle_record_customs,
            "tax_compliance.draft_return": self._handle_draft_return,
            "tax_compliance.file_return": self._handle_file_return,
            "tax_compliance.settle_return": self._handle_settle_return,
            "tax_compliance.record_payment": self._handle_record_payment,
            "tax_compliance.export_pdf": self._handle_export_pdf,
            "tax_compliance.export_dsf": self._handle_export_dsf,
            "tax_compliance.refresh": self.reload,
        }

    def ribbon_state(self) -> dict:
        return {
            "tax_compliance.generate_vat_calendar": self._generate_button.isEnabled(),
            "tax_compliance.generate_cit_installments": self._cit_button.isEnabled(),
            "tax_compliance.generate_withholding_calendar": self._more_generators_button.isEnabled(),
            "tax_compliance.generate_patente_obligation": self._more_generators_button.isEnabled(),
            "tax_compliance.generate_tsr_calendar": self._more_generators_button.isEnabled(),
            "tax_compliance.record_customs_duty": self._more_generators_button.isEnabled(),
            "tax_compliance.draft_return": self._draft_button.isEnabled(),
            "tax_compliance.file_return": self._file_button.isEnabled(),
            "tax_compliance.settle_return": self._settle_button.isEnabled(),
            "tax_compliance.record_payment": self._payment_button.isEnabled(),
            "tax_compliance.export_pdf": self._export_pdf_button.isEnabled(),
            "tax_compliance.export_dsf": self._dsf_button.isEnabled(),
            "tax_compliance.refresh": True,
        }

    def _handle_draft_return(self) -> None:
        active = self._active_company()
        ob = self._selected_obligation()
        if active is None or ob is None:
            return

        # Patente / TSR / Customs use a one-shot "file assessed return"
        # workflow — there is no draft step, the user enters the
        # assessed amount directly and the return is created already
        # in the FILED state.
        if ob.tax_type_code in ALL_ASSESSED_RETURN_TAX_TYPES:
            dialog = FileAssessedTaxReturnDialog(
                self._service_registry, active.company_id, ob, parent=self
            )
            if dialog.exec() and dialog.filed_return() is not None:
                show_info(
                    self,
                    "File Assessed Return",
                    f"{ob.tax_type_code} return filed.",
                )
                self.reload()
            return

        # VAT (and any future aggregating tax type) keeps the draft
        # → file workflow.
        try:
            self._service_registry.tax_return_service.draft_vat_return(
                active.company_id,
                DraftVATReturnCommand(obligation_id=ob.id),
            )
        except ValidationError as exc:
            show_error(self, "Draft VAT Return", str(exc))
            return
        except (NotFoundError, ConflictError, PermissionDeniedError) as exc:
            show_error(self, "Draft VAT Return", str(exc))
            return
        except Exception as exc:  # pragma: no cover - defensive
            show_error(self, "Draft VAT Return", f"Could not draft return.\n\n{exc}")
            return

        show_info(self, "Draft VAT Return", "Draft return generated.")
        self.reload()

    def _handle_file_return(self) -> None:
        active = self._active_company()
        rt = self._selected_return()
        if active is None or rt is None:
            return
        dialog = FileTaxReturnDialog(
            self._service_registry, active.company_id, rt, parent=self
        )
        if dialog.exec() and dialog.filed_return() is not None:
            show_info(self, "File Return", "Return filed.")
            self.reload()

    def _handle_settle_return(self) -> None:
        active = self._active_company()
        rt = self._selected_return()
        if active is None or rt is None:
            return
        dialog = SettleVATReturnDialog(
            self._service_registry, active.company_id, rt, parent=self
        )
        if dialog.exec() and dialog.settlement_result() is not None:
            show_info(self, "Settle VAT Return", "Settlement journal posted.")
            self.reload()

    def _handle_record_payment(self) -> None:
        active = self._active_company()
        rt = self._selected_return()
        if active is None or rt is None:
            return
        dialog = RecordTaxPaymentDialog(
            self._service_registry, active.company_id, rt, parent=self
        )
        if dialog.exec() and dialog.recorded_payment() is not None:
            show_info(self, "Tax Payment", "Payment recorded.")
            self.reload()

    def _handle_export_dsf(self) -> None:
        active = self._active_company()
        if active is None:
            return
        dialog = DSFExportDialog(
            self._service_registry,
            active.company_id,
            active.company_name,
            parent=self,
        )
        if dialog.exec():
            result = dialog.export_result()
            if result is not None:
                show_info(
                    self,
                    "DSF Export",
                    f"DSF written to:\n{result.output_path}",
                )

    def _handle_export_pdf(self) -> None:
        active = self._active_company()
        rt = self._selected_return()
        if active is None or rt is None:
            return
        dialog = ExportTaxReturnPDFDialog(
            self._service_registry,
            active.company_id,
            rt,
            active.company_name,
            parent=self,
        )
        if dialog.exec() and dialog.export_result() is not None:
            result = dialog.export_result()
            assert result is not None
            show_info(
                self,
                "Export Tax Return PDF",
                f"PDF written to:\n{result.output_path}",
            )

    # ── Helpers ───────────────────────────────────────────────────────

    def _active_company(self):
        return self._service_registry.company_context_service.get_active_company()
