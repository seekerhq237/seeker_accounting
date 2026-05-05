"""Tests for the WorkflowStepper component."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from seeker_accounting.shared.ui.components import (
    WorkflowStep,
    WorkflowStepper,
)


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _steps() -> list[WorkflowStep]:
    return [
        WorkflowStep(key="obligation", label="Obligation"),
        WorkflowStep(key="draft", label="Draft"),
        WorkflowStep(key="filed", label="Filed"),
        WorkflowStep(key="settled", label="Settled"),
    ]


def _click(widget: WorkflowStepper, x: int, y: int) -> None:
    pos = QPoint(x, y)
    press = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        pos,
        widget.mapToGlobal(pos),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    widget.mousePressEvent(press)


def test_default_state_pending_and_click_emits(qapp: QApplication) -> None:
    stepper = WorkflowStepper(_steps())
    stepper.setFixedSize(800, 64)
    stepper.show()
    qapp.processEvents()

    for step in stepper.steps():
        assert step.state == "pending"

    received: list[str] = []
    stepper.step_clicked.connect(received.append)

    # Click in column 1 (Draft is index 1, columns evenly split → 200..400).
    _click(stepper, 300, 32)
    assert received == ["draft"]


def test_set_step_state_repaints_without_error(qapp: QApplication) -> None:
    stepper = WorkflowStepper(_steps())
    stepper.setFixedSize(800, 64)
    stepper.set_step_state("draft", "complete")
    assert stepper.steps()[1].state == "complete"
    stepper.repaint()  # should not raise


def test_set_active_step_cascades_states(qapp: QApplication) -> None:
    stepper = WorkflowStepper(_steps())
    stepper.set_active_step("filed")
    states = {s.key: s.state for s in stepper.steps()}
    assert states["obligation"] == "complete"
    assert states["draft"] == "complete"
    assert states["filed"] == "active"
    assert states["settled"] == "pending"


def test_disabled_step_does_not_emit(qapp: QApplication) -> None:
    steps = _steps()
    steps[1] = WorkflowStep(key="draft", label="Draft", enabled=False)
    stepper = WorkflowStepper(steps)
    stepper.setFixedSize(800, 64)
    stepper.show()
    qapp.processEvents()

    received: list[str] = []
    stepper.step_clicked.connect(received.append)
    # Click on the disabled (Draft) column.
    _click(stepper, 300, 32)
    assert received == []


def test_paint_event_does_not_raise(qapp: QApplication) -> None:
    stepper = WorkflowStepper(
        [
            WorkflowStep(key="a", label="A", state="complete", badge="3"),
            WorkflowStep(key="b", label="B", state="active", description="now"),
            WorkflowStep(key="c", label="C", state="pending"),
            WorkflowStep(key="d", label="D", state="blocked"),
            WorkflowStep(key="e", label="E", state="skipped"),
        ]
    )
    stepper.setFixedSize(800, 64)
    stepper.show()
    qapp.processEvents()
    stepper.repaint()  # exercise paintEvent
