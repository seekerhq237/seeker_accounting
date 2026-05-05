"""Centralized window-size constraints for dialogs and workbench windows.

This module replaces scattered numeric ``resize(width, height)`` literals with
named tokens. Tokens can be reviewed, tuned, or mapped to responsive policies
without hunting through feature UI files.
"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import QWidget


@dataclass(frozen=True, slots=True)
class WindowSizeToken:
    key: str
    width: int
    height: int


WINDOW_SIZE_TOKENS: dict[str, WindowSizeToken] = {
    "app.shell.child.windows.child.window.base.0": WindowSizeToken("app.shell.child.windows.child.window.base.0", 1080, 720),
    "app.shell.license.dialog.0": WindowSizeToken("app.shell.license.dialog.0", 520, 380),
    "modules.accounting.chart.of.accounts.ui.account.form.dialog.0": WindowSizeToken("modules.accounting.chart.of.accounts.ui.account.form.dialog.0", 680, 490),
    "modules.accounting.chart.of.accounts.ui.chart.customization.wizard.dialog.0": WindowSizeToken("modules.accounting.chart.of.accounts.ui.chart.customization.wizard.dialog.0", 1180, 820),
    "modules.accounting.chart.of.accounts.ui.chart.import.dialog.0": WindowSizeToken("modules.accounting.chart.of.accounts.ui.chart.import.dialog.0", 760, 620),
    "modules.accounting.fiscal.periods.ui.fiscal.year.dialog.0": WindowSizeToken("modules.accounting.fiscal.periods.ui.fiscal.year.dialog.0", 540, 0),
    "modules.accounting.fiscal.periods.ui.fiscal.year.setup.wizard.dialog.0": WindowSizeToken("modules.accounting.fiscal.periods.ui.fiscal.year.setup.wizard.dialog.0", 640, 540),
    "modules.accounting.fiscal.periods.ui.generate.periods.dialog.0": WindowSizeToken("modules.accounting.fiscal.periods.ui.generate.periods.dialog.0", 560, 320),
    "modules.accounting.journals.ui.account.picker.dialog.0": WindowSizeToken("modules.accounting.journals.ui.account.picker.dialog.0", 640, 480),
    "modules.accounting.journals.ui.journal.entry.dialog.0": WindowSizeToken("modules.accounting.journals.ui.journal.entry.dialog.0", 960, 680),
    "modules.accounting.journals.ui.line.allocation.dialog.0": WindowSizeToken("modules.accounting.journals.ui.line.allocation.dialog.0", 420, 320),
    "modules.accounting.reference.data.ui.account.role.mapping.dialog.0": WindowSizeToken("modules.accounting.reference.data.ui.account.role.mapping.dialog.0", 760, 560),
    "modules.accounting.reference.data.ui.document.sequence.dialog.0": WindowSizeToken("modules.accounting.reference.data.ui.document.sequence.dialog.0", 520, 0),
    "modules.accounting.reference.data.ui.payment.term.dialog.0": WindowSizeToken("modules.accounting.reference.data.ui.payment.term.dialog.0", 480, 0),
    "modules.accounting.reference.data.ui.tax.code.account.mapping.dialog.0": WindowSizeToken("modules.accounting.reference.data.ui.tax.code.account.mapping.dialog.0", 980, 620),
    "modules.accounting.reference.data.ui.tax.code.dialog.0": WindowSizeToken("modules.accounting.reference.data.ui.tax.code.dialog.0", 620, 520),
    "modules.administration.ui.abnormal.shutdown.dialog.0": WindowSizeToken("modules.administration.ui.abnormal.shutdown.dialog.0", 540, 420),
    "modules.administration.ui.admin.abnormal.session.dialog.0": WindowSizeToken("modules.administration.ui.admin.abnormal.session.dialog.0", 760, 460),
    "modules.administration.ui.backup.import.preview.dialog.0": WindowSizeToken("modules.administration.ui.backup.import.preview.dialog.0", 820, 620),
    "modules.administration.ui.login.dialog.0": WindowSizeToken("modules.administration.ui.login.dialog.0", 420, 340),
    "modules.administration.ui.permission.assignment.dialog.0": WindowSizeToken("modules.administration.ui.permission.assignment.dialog.0", 408, 448),
    "modules.administration.ui.profile.edit.dialog.0": WindowSizeToken("modules.administration.ui.profile.edit.dialog.0", 440, 420),
    "modules.administration.ui.role.assignment.dialog.0": WindowSizeToken("modules.administration.ui.role.assignment.dialog.0", 500, 420),
    "modules.administration.ui.role.edit.dialog.0": WindowSizeToken("modules.administration.ui.role.edit.dialog.0", 460, 340),
    "modules.budgeting.ui.budget.editor.dialog.0": WindowSizeToken("modules.budgeting.ui.budget.editor.dialog.0", 1100, 720),
    "modules.budgeting.ui.budget.lines.dialog.0": WindowSizeToken("modules.budgeting.ui.budget.lines.dialog.0", 620, 560),
    "modules.budgeting.ui.budget.lines.dialog.1": WindowSizeToken("modules.budgeting.ui.budget.lines.dialog.1", 980, 580),
    "modules.budgeting.ui.budget.version.dialog.0": WindowSizeToken("modules.budgeting.ui.budget.version.dialog.0", 600, 500),
    "modules.budgeting.ui.budget.version.dialog.1": WindowSizeToken("modules.budgeting.ui.budget.version.dialog.1", 940, 560),
    "modules.budgeting.ui.copy.budget.version.dialog.0": WindowSizeToken("modules.budgeting.ui.copy.budget.version.dialog.0", 520, 430),
    "modules.companies.ui.company.form.dialog.0": WindowSizeToken("modules.companies.ui.company.form.dialog.0", 580, 600),
    "modules.companies.ui.company.form.dialog.1": WindowSizeToken("modules.companies.ui.company.form.dialog.1", 580, 600),
    "modules.companies.ui.company.preferences.dialog.0": WindowSizeToken("modules.companies.ui.company.preferences.dialog.0", 480, 500),
    "modules.companies.ui.company.selector.dialog.0": WindowSizeToken("modules.companies.ui.company.selector.dialog.0", 700, 400),
    "modules.companies.ui.system.admin.dialog.0": WindowSizeToken("modules.companies.ui.system.admin.dialog.0", 900, 560),
    "modules.contracts.projects.ui.contract.billing.schedule.panel.0": WindowSizeToken("modules.contracts.projects.ui.contract.billing.schedule.panel.0", 1050, 540),
    "modules.contracts.projects.ui.contract.change.order.dialog.0": WindowSizeToken("modules.contracts.projects.ui.contract.change.order.dialog.0", 640, 520),
    "modules.contracts.projects.ui.contract.change.order.dialog.1": WindowSizeToken("modules.contracts.projects.ui.contract.change.order.dialog.1", 880, 560),
    "modules.contracts.projects.ui.contract.customer.advances.panel.0": WindowSizeToken("modules.contracts.projects.ui.contract.customer.advances.panel.0", 520, 480),
    "modules.contracts.projects.ui.contract.form.dialog.0": WindowSizeToken("modules.contracts.projects.ui.contract.form.dialog.0", 780, 640),
    "modules.contracts.projects.ui.contract.lines.panel.0": WindowSizeToken("modules.contracts.projects.ui.contract.lines.panel.0", 920, 540),
    "modules.contracts.projects.ui.contract.progress.claims.panel.0": WindowSizeToken("modules.contracts.projects.ui.contract.progress.claims.panel.0", 560, 640),
    "modules.contracts.projects.ui.contract.progress.claims.panel.1": WindowSizeToken("modules.contracts.projects.ui.contract.progress.claims.panel.1", 520, 480),
    "modules.contracts.projects.ui.contract.receipt.allocations.panel.0": WindowSizeToken("modules.contracts.projects.ui.contract.receipt.allocations.panel.0", 560, 560),
    "modules.contracts.projects.ui.contract.retention.panel.0": WindowSizeToken("modules.contracts.projects.ui.contract.retention.panel.0", 480, 380),
    "modules.contracts.projects.ui.project.cost.code.dialog.0": WindowSizeToken("modules.contracts.projects.ui.project.cost.code.dialog.0", 560, 460),
    "modules.contracts.projects.ui.project.cost.code.dialog.1": WindowSizeToken("modules.contracts.projects.ui.project.cost.code.dialog.1", 820, 520),
    "modules.contracts.projects.ui.project.form.dialog.0": WindowSizeToken("modules.contracts.projects.ui.project.form.dialog.0", 780, 620),
    "modules.contracts.projects.ui.project.job.dialog.0": WindowSizeToken("modules.contracts.projects.ui.project.job.dialog.0", 600, 520),
    "modules.contracts.projects.ui.project.job.dialog.1": WindowSizeToken("modules.contracts.projects.ui.project.job.dialog.1", 900, 560),
    "modules.customers.ui.customer.dialog.0": WindowSizeToken("modules.customers.ui.customer.dialog.0", 780, 620),
    "modules.customers.ui.customer.group.dialog.0": WindowSizeToken("modules.customers.ui.customer.group.dialog.0", 700, 520),
    "modules.fixed.assets.ui.asset.category.dialog.0": WindowSizeToken("modules.fixed.assets.ui.asset.category.dialog.0", 460, 460),
    "modules.fixed.assets.ui.asset.dialog.0": WindowSizeToken("modules.fixed.assets.ui.asset.dialog.0", 560, 0),
    "modules.fixed.assets.ui.depreciation.run.dialog.0": WindowSizeToken("modules.fixed.assets.ui.depreciation.run.dialog.0", 720, 560),
    "modules.fixed.assets.ui.depreciation.schedule.preview.dialog.0": WindowSizeToken("modules.fixed.assets.ui.depreciation.schedule.preview.dialog.0", 860, 620),
    "modules.inventory.ui.inventory.document.dialog.0": WindowSizeToken("modules.inventory.ui.inventory.document.dialog.0", 1020, 720),
    "modules.inventory.ui.inventory.locations.page.0": WindowSizeToken("modules.inventory.ui.inventory.locations.page.0", 420, 280),
    "modules.inventory.ui.item.categories.page.0": WindowSizeToken("modules.inventory.ui.item.categories.page.0", 420, 280),
    "modules.inventory.ui.item.dialog.0": WindowSizeToken("modules.inventory.ui.item.dialog.0", 580, 620),
    "modules.inventory.ui.units.of.measure.page.0": WindowSizeToken("modules.inventory.ui.units.of.measure.page.0", 420, 340),
    "modules.inventory.ui.uom.categories.page.0": WindowSizeToken("modules.inventory.ui.uom.categories.page.0", 420, 280),
    "modules.job.costing.ui.project.commitment.dialog.0": WindowSizeToken("modules.job.costing.ui.project.commitment.dialog.0", 640, 560),
    "modules.job.costing.ui.project.commitment.dialog.1": WindowSizeToken("modules.job.costing.ui.project.commitment.dialog.1", 1020, 560),
    "modules.job.costing.ui.project.commitment.lines.dialog.0": WindowSizeToken("modules.job.costing.ui.project.commitment.lines.dialog.0", 620, 520),
    "modules.job.costing.ui.project.commitment.lines.dialog.1": WindowSizeToken("modules.job.costing.ui.project.commitment.lines.dialog.1", 940, 500),
    "modules.payroll.ui.dialogs.apply.statutory.pack.dialog.0": WindowSizeToken("modules.payroll.ui.dialogs.apply.statutory.pack.dialog.0", 520, 420),
    "modules.payroll.ui.dialogs.company.payroll.settings.dialog.0": WindowSizeToken("modules.payroll.ui.dialogs.company.payroll.settings.dialog.0", 520, 560),
    "modules.payroll.ui.dialogs.department.dialog.0": WindowSizeToken("modules.payroll.ui.dialogs.department.dialog.0", 380, 220),
    "modules.payroll.ui.dialogs.department.dialog.1": WindowSizeToken("modules.payroll.ui.dialogs.department.dialog.1", 580, 440),
    "modules.payroll.ui.dialogs.employee.form.dialog.0": WindowSizeToken("modules.payroll.ui.dialogs.employee.form.dialog.0", 500, 560),
    "modules.payroll.ui.dialogs.payroll.component.form.dialog.0": WindowSizeToken("modules.payroll.ui.dialogs.payroll.component.form.dialog.0", 500, 480),
    "modules.payroll.ui.dialogs.payroll.project.allocations.dialog.0": WindowSizeToken("modules.payroll.ui.dialogs.payroll.project.allocations.dialog.0", 1180, 680),
    "modules.payroll.ui.dialogs.payroll.rule.brackets.dialog.0": WindowSizeToken("modules.payroll.ui.dialogs.payroll.rule.brackets.dialog.0", 400, 340),
    "modules.payroll.ui.dialogs.payroll.rule.brackets.dialog.1": WindowSizeToken("modules.payroll.ui.dialogs.payroll.rule.brackets.dialog.1", 760, 480),
    "modules.payroll.ui.dialogs.payroll.rule.set.form.dialog.0": WindowSizeToken("modules.payroll.ui.dialogs.payroll.rule.set.form.dialog.0", 480, 440),
    "modules.payroll.ui.dialogs.payslip.preview.dialog.0": WindowSizeToken("modules.payroll.ui.dialogs.payslip.preview.dialog.0", 860, 1020),
    "modules.payroll.ui.dialogs.position.dialog.0": WindowSizeToken("modules.payroll.ui.dialogs.position.dialog.0", 380, 220),
    "modules.payroll.ui.dialogs.position.dialog.1": WindowSizeToken("modules.payroll.ui.dialogs.position.dialog.1", 580, 440),
    "modules.payroll.ui.dialogs.remittance.editor.dialog.0": WindowSizeToken("modules.payroll.ui.dialogs.remittance.editor.dialog.0", 960, 640),
    "modules.payroll.ui.dialogs.validation.check.detail.dialog.0": WindowSizeToken("modules.payroll.ui.dialogs.validation.check.detail.dialog.0", 680, 580),
    "modules.payroll.ui.wizards.compensation.change.wizard.0": WindowSizeToken("modules.payroll.ui.wizards.compensation.change.wizard.0", 820, 660),
    "modules.payroll.ui.wizards.employee.hire.wizard.0": WindowSizeToken("modules.payroll.ui.wizards.employee.hire.wizard.0", 720, 620),
    "modules.payroll.ui.wizards.employee.payroll.setup.wizard.0": WindowSizeToken("modules.payroll.ui.wizards.employee.payroll.setup.wizard.0", 940, 680),
    "modules.payroll.ui.wizards.payroll.activation.wizard.0": WindowSizeToken("modules.payroll.ui.wizards.payroll.activation.wizard.0", 680, 580),
    "modules.purchases.ui.purchase.bill.dialog.0": WindowSizeToken("modules.purchases.ui.purchase.bill.dialog.0", 1040, 720),
    "modules.purchases.ui.purchase.credit.note.dialog.0": WindowSizeToken("modules.purchases.ui.purchase.credit.note.dialog.0", 920, 680),
    "modules.purchases.ui.purchase.order.dialog.0": WindowSizeToken("modules.purchases.ui.purchase.order.dialog.0", 960, 700),
    "modules.purchases.ui.purchase.order.dialog.1": WindowSizeToken("modules.purchases.ui.purchase.order.dialog.1", 440, 280),
    "modules.purchases.ui.supplier.payment.dialog.0": WindowSizeToken("modules.purchases.ui.supplier.payment.dialog.0", 920, 640),
    "modules.reporting.ui.dialogs.ias.income.statement.mapping.dialog.0": WindowSizeToken("modules.reporting.ui.dialogs.ias.income.statement.mapping.dialog.0", 520, 340),
    "modules.reporting.ui.dialogs.ias.income.statement.window.0": WindowSizeToken("modules.reporting.ui.dialogs.ias.income.statement.window.0", 540, 380),
    "modules.sales.ui.customer.quote.dialog.0": WindowSizeToken("modules.sales.ui.customer.quote.dialog.0", 960, 700),
    "modules.sales.ui.customer.quote.dialog.1": WindowSizeToken("modules.sales.ui.customer.quote.dialog.1", 440, 260),
    "modules.sales.ui.customer.receipt.dialog.0": WindowSizeToken("modules.sales.ui.customer.receipt.dialog.0", 920, 640),
    "modules.sales.ui.sales.credit.note.dialog.0": WindowSizeToken("modules.sales.ui.sales.credit.note.dialog.0", 960, 700),
    "modules.sales.ui.sales.invoice.dialog.0": WindowSizeToken("modules.sales.ui.sales.invoice.dialog.0", 1040, 720),
    "modules.sales.ui.sales.order.dialog.0": WindowSizeToken("modules.sales.ui.sales.order.dialog.0", 960, 700),
    "modules.sales.ui.sales.order.dialog.1": WindowSizeToken("modules.sales.ui.sales.order.dialog.1", 440, 280),
    "modules.suppliers.ui.supplier.dialog.0": WindowSizeToken("modules.suppliers.ui.supplier.dialog.0", 780, 620),
    "modules.suppliers.ui.supplier.group.dialog.0": WindowSizeToken("modules.suppliers.ui.supplier.group.dialog.0", 700, 520),
    "modules.taxation.ui.company.tax.profile.dialog.0": WindowSizeToken("modules.taxation.ui.company.tax.profile.dialog.0", 720, 640),
    "modules.taxation.ui.tax.compliance.dialogs.0": WindowSizeToken("modules.taxation.ui.tax.compliance.dialogs.0", 520, 320),
    "modules.taxation.ui.tax.compliance.dialogs.1": WindowSizeToken("modules.taxation.ui.tax.compliance.dialogs.1", 520, 320),
    "modules.taxation.ui.tax.compliance.dialogs.10": WindowSizeToken("modules.taxation.ui.tax.compliance.dialogs.10", 560, 380),
    "modules.taxation.ui.tax.compliance.dialogs.11": WindowSizeToken("modules.taxation.ui.tax.compliance.dialogs.11", 560, 280),
    "modules.taxation.ui.tax.compliance.dialogs.2": WindowSizeToken("modules.taxation.ui.tax.compliance.dialogs.2", 560, 360),
    "modules.taxation.ui.tax.compliance.dialogs.3": WindowSizeToken("modules.taxation.ui.tax.compliance.dialogs.3", 560, 420),
    "modules.taxation.ui.tax.compliance.dialogs.4": WindowSizeToken("modules.taxation.ui.tax.compliance.dialogs.4", 560, 460),
    "modules.taxation.ui.tax.compliance.dialogs.5": WindowSizeToken("modules.taxation.ui.tax.compliance.dialogs.5", 640, 540),
    "modules.taxation.ui.tax.compliance.dialogs.6": WindowSizeToken("modules.taxation.ui.tax.compliance.dialogs.6", 720, 560),
    "modules.taxation.ui.tax.compliance.dialogs.7": WindowSizeToken("modules.taxation.ui.tax.compliance.dialogs.7", 520, 320),
    "modules.taxation.ui.tax.compliance.dialogs.8": WindowSizeToken("modules.taxation.ui.tax.compliance.dialogs.8", 520, 340),
    "modules.taxation.ui.tax.compliance.dialogs.9": WindowSizeToken("modules.taxation.ui.tax.compliance.dialogs.9", 520, 320),
    "modules.taxation.ui.tax.return.detail.dialog.0": WindowSizeToken("modules.taxation.ui.tax.return.detail.dialog.0", 960, 800),
    "modules.taxation.ui.vat.exception.report.dialog.0": WindowSizeToken("modules.taxation.ui.vat.exception.report.dialog.0", 900, 560),
    "modules.taxation.ui.vat.line.drilldown.dialog.0": WindowSizeToken("modules.taxation.ui.vat.line.drilldown.dialog.0", 820, 480),
    "modules.taxation.ui.withholding.certificates.dialogs.0": WindowSizeToken("modules.taxation.ui.withholding.certificates.dialogs.0", 640, 620),
    "modules.taxation.ui.withholding.certificates.dialogs.1": WindowSizeToken("modules.taxation.ui.withholding.certificates.dialogs.1", 640, 620),
    "modules.taxation.ui.withholding.certificates.dialogs.2": WindowSizeToken("modules.taxation.ui.withholding.certificates.dialogs.2", 520, 320),
    "modules.taxation.ui.withholding.certificates.dialogs.3": WindowSizeToken("modules.taxation.ui.withholding.certificates.dialogs.3", 620, 460),
    "modules.treasury.ui.financial.account.dialog.0": WindowSizeToken("modules.treasury.ui.financial.account.dialog.0", 600, 450),
    "modules.treasury.ui.manual.statement.line.dialog.0": WindowSizeToken("modules.treasury.ui.manual.statement.line.dialog.0", 500, 400),
    "modules.treasury.ui.statement.import.dialog.0": WindowSizeToken("modules.treasury.ui.statement.import.dialog.0", 550, 350),
    "modules.treasury.ui.treasury.transaction.dialog.0": WindowSizeToken("modules.treasury.ui.treasury.transaction.dialog.0", 800, 600),
    "modules.treasury.ui.treasury.transfer.dialog.0": WindowSizeToken("modules.treasury.ui.treasury.transfer.dialog.0", 650, 480),
    "platform.wizards.host.dialog.0": WindowSizeToken("platform.wizards.host.dialog.0", 940, 620),
    "shared.ui.dialogs.0": WindowSizeToken("shared.ui.dialogs.0", 520, 320),
    "shared.ui.guided.resolution.dialog.0": WindowSizeToken("shared.ui.guided.resolution.dialog.0", 560, 360),
    "shared.ui.help.overlay.0": WindowSizeToken("shared.ui.help.overlay.0", 520, 460),
}


def get_window_size_token(key: str) -> WindowSizeToken:
    try:
        return WINDOW_SIZE_TOKENS[key]
    except KeyError as exc:
        raise KeyError(f"Unknown window size token: {key}") from exc


def apply_window_size(widget: QWidget, key: str) -> None:
    token = get_window_size_token(key)
    widget.resize(token.width, token.height)
