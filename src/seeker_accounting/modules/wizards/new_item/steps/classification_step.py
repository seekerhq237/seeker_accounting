"""Step 2 — Classification (UOM, category, cost method, reorder level)."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.modules.wizards.new_item import state_keys as K
from seeker_accounting.platform.wizards import (
    StepValidationResult,
    WizardContext,
    WizardState,
    WizardStep,
)


class ClassificationStep(WizardStep):
    key = "classification"
    title = "Classification"
    subtitle = "Unit of measure, category, and cost method."

    def __init__(self) -> None:
        super().__init__()
        self._uom: QComboBox | None = None
        self._category: QComboBox | None = None
        self._cost_method: QComboBox | None = None
        self._reorder: QLineEdit | None = None

    def build_widget(self, parent: QWidget | None = None) -> QWidget:
        root = QWidget(parent)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)
        form = QFormLayout()

        self._uom = QComboBox(root)
        form.addRow(QLabel("Unit of measure:", root), self._uom)

        self._category = QComboBox(root)
        form.addRow(QLabel("Category:", root), self._category)

        self._cost_method = QComboBox(root)
        self._cost_method.addItem("(none — non-stock)", None)
        self._cost_method.addItem("Weighted average", "weighted_average")
        form.addRow(QLabel("Cost method:", root), self._cost_method)

        self._reorder = QLineEdit(root)
        self._reorder.setPlaceholderText("0")
        form.addRow(QLabel("Reorder level qty:", root), self._reorder)

        outer.addLayout(form)
        outer.addStretch(1)
        return root

    def load(self, context: WizardContext, state: WizardState) -> None:
        company_id = context.require_company_id()
        if self._uom is not None and self._uom.count() == 0:
            for u in context.service_registry.unit_of_measure_service.list_units_of_measure(
                company_id, active_only=True
            ):
                self._uom.addItem(f"{u.code} \u2014 {u.name}", (u.id, u.code))
            prior = state.get(K.KEY_UNIT_OF_MEASURE_ID)
            if isinstance(prior, int):
                for i in range(self._uom.count()):
                    data = self._uom.itemData(i)
                    if isinstance(data, tuple) and data[0] == prior:
                        self._uom.setCurrentIndex(i)
                        break
        if self._category is not None and self._category.count() == 0:
            self._category.addItem("(none)", None)
            for c in context.service_registry.item_category_service.list_item_categories(
                company_id, active_only=True
            ):
                self._category.addItem(f"{c.code} \u2014 {c.name}", c.id)
            prior_cat = state.get(K.KEY_ITEM_CATEGORY_ID)
            if isinstance(prior_cat, int):
                idx = self._category.findData(prior_cat)
                if idx >= 0:
                    self._category.setCurrentIndex(idx)
        if self._cost_method is not None:
            type_code = state.get(K.KEY_ITEM_TYPE_CODE)
            if type_code == "stock" and not state.get(K.KEY_INVENTORY_COST_METHOD_CODE):
                self._cost_method.setCurrentIndex(self._cost_method.findData("weighted_average"))
            else:
                prior_cm = state.get(K.KEY_INVENTORY_COST_METHOD_CODE)
                if isinstance(prior_cm, str):
                    idx = self._cost_method.findData(prior_cm)
                    if idx >= 0:
                        self._cost_method.setCurrentIndex(idx)
        if self._reorder is not None and state.get(K.KEY_REORDER_LEVEL_QUANTITY):
            self._reorder.setText(str(state[K.KEY_REORDER_LEVEL_QUANTITY]))

    def write_back(self, state: WizardState) -> None:
        if self._uom is not None:
            data = self._uom.currentData()
            if isinstance(data, tuple):
                state[K.KEY_UNIT_OF_MEASURE_ID] = int(data[0])
                state[K.KEY_UNIT_OF_MEASURE_CODE] = str(data[1])
            else:
                state[K.KEY_UNIT_OF_MEASURE_ID] = None
                state[K.KEY_UNIT_OF_MEASURE_CODE] = "UNIT"
        if self._category is not None:
            data = self._category.currentData()
            state[K.KEY_ITEM_CATEGORY_ID] = int(data) if isinstance(data, int) else None
        if self._cost_method is not None:
            data = self._cost_method.currentData()
            state[K.KEY_INVENTORY_COST_METHOD_CODE] = str(data) if data else None
        if self._reorder is not None:
            state[K.KEY_REORDER_LEVEL_QUANTITY] = self._reorder.text().strip() or None

    def validate(self, context: WizardContext, state: WizardState) -> StepValidationResult:
        if not isinstance(state.get(K.KEY_UNIT_OF_MEASURE_ID), int):
            return StepValidationResult.fail("Pick a unit of measure.")
        type_code = state.get(K.KEY_ITEM_TYPE_CODE)
        if type_code == "stock" and not state.get(K.KEY_INVENTORY_COST_METHOD_CODE):
            return StepValidationResult.fail("Stock items require a cost method (e.g. weighted average).")
        rq = state.get(K.KEY_REORDER_LEVEL_QUANTITY)
        if rq:
            try:
                if Decimal(str(rq)) < 0:
                    return StepValidationResult.fail("Reorder level cannot be negative.")
            except (InvalidOperation, ValueError):
                return StepValidationResult.fail("Reorder level must be a number.")
        return StepValidationResult.ok()

    def preview(self, context: WizardContext, state: WizardState) -> str | None:
        bits = [state.get(K.KEY_UNIT_OF_MEASURE_CODE), state.get(K.KEY_INVENTORY_COST_METHOD_CODE)]
        return " \u00b7 ".join(str(b) for b in bits if b) or None
