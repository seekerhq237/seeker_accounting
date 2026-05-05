"""WizardShell — Phase 1 Slice 6 (Wizard framework v2).

A reusable multi-step dialog shell for long-running business processes
(Hire, Termination, Compensation Change, etc.). The shell owns:

- a declarative ``WizardStepDescriptor`` list with ``id``, ``title``,
  ``optional`` and ``gate`` callable;
- the visual stepper indicator (``WorkflowStepper``);
- the central content area, populated lazily via ``set_step_widget``;
- a side panel for blocking issues on the current step;
- footer with **Back / Next / Finish / Cancel** buttons whose enabled
  state is driven by the gate callable and per-step state.

It is **business-domain agnostic**: the shell never knows what the
steps mean, never persists data, never validates fields. The host
dialog (e.g. the Hire BP wizard in P4.S2) plugs business logic into
the lifecycle signals:

- ``next_requested(step_id)`` — host should validate & save, then call
  :meth:`advance_step` on success.
- ``back_requested(step_id)`` — host may save partial data, then call
  :meth:`go_back`.
- ``jump_requested(step_id)`` — host may allow if jump is valid.
- ``finish_requested()`` — host should perform the terminal action.
- ``cancel_requested()`` — host should ask to save draft / abandon.

Per the project's design rules: no ``resize(...)``, all sizing comes
from layouts and tokens; QSS via ``#WizardShell`` selector.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.shared.ui.components.inline_issue_band import (
    InlineIssueBand,
    ValidationIssue,
)
from seeker_accounting.shared.ui.components.workflow_stepper import (
    WorkflowStep,
    WorkflowStepState,
    WorkflowStepper,
)
from seeker_accounting.shared.ui.styles.tokens import DEFAULT_TOKENS

WizardStepStatus = Literal["pending", "active", "complete", "issues", "skipped"]

# Map wizard step status → workflow stepper visual state.
_STATUS_TO_STEPPER: dict[WizardStepStatus, WorkflowStepState] = {
    "pending": "pending",
    "active": "active",
    "complete": "complete",
    "issues": "blocked",
    "skipped": "skipped",
}


@dataclass(frozen=True, slots=True)
class WizardStepDescriptor:
    """Declarative description of one wizard step.

    ``gate`` is consulted whenever the user attempts to *jump to* this
    step from a non-adjacent step. It receives the wizard's current
    state map (``{step_id: status}``) and must return ``True`` to allow
    the jump. Adjacent forward/back navigation always uses the host
    callbacks instead.
    """

    id: str
    title: str
    description: str = ""
    optional: bool = False
    gate: Callable[[dict[str, WizardStepStatus]], bool] | None = None


@dataclass(slots=True)
class _StepRecord:
    descriptor: WizardStepDescriptor
    status: WizardStepStatus = "pending"
    widget: QWidget | None = None
    issues: list[ValidationIssue] = field(default_factory=list)


class WizardShell(QDialog):
    """Reusable multi-step business-process dialog.

    Subclassing is supported but not required: most hosts compose the
    shell, register step widgets, and wire the lifecycle signals.
    """

    next_requested = Signal(str)
    back_requested = Signal(str)
    jump_requested = Signal(str)
    finish_requested = Signal()
    cancel_requested = Signal()
    step_changed = Signal(str)

    def __init__(
        self,
        title: str,
        steps: Sequence[WizardStepDescriptor],
        *,
        parent: QWidget | None = None,
        primary_label: str = "Next",
        finish_label: str = "Finish",
        cancel_label: str = "Cancel",
        back_label: str = "Back",
        min_width: int = 720,
        min_height: int = 520,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("WizardShell")
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumSize(min_width, min_height)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)

        if not steps:
            raise ValueError("WizardShell requires at least one step.")

        self._records: list[_StepRecord] = [
            _StepRecord(descriptor=s) for s in steps
        ]
        self._current_index: int = 0
        self._records[0].status = "active"

        spacing = DEFAULT_TOKENS.spacing

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Header: title + stepper ──────────────────────────────────
        header = QFrame(self)
        header.setObjectName("WizardShellHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(
            spacing.dialog_padding,
            spacing.dialog_padding,
            spacing.dialog_padding,
            spacing.compact_gap,
        )
        header_layout.setSpacing(spacing.compact_gap)

        self._title_label = QLabel(title, header)
        self._title_label.setObjectName("WizardShellTitle")
        header_layout.addWidget(self._title_label)

        self._stepper = WorkflowStepper(
            steps=self._build_workflow_steps(),
            clickable=True,
            parent=header,
        )
        self._stepper.step_clicked.connect(self._on_stepper_clicked)
        header_layout.addWidget(self._stepper)

        outer.addWidget(header)

        # ── Issue band (top-of-content) ──────────────────────────────
        self._issue_band = InlineIssueBand(self)
        self._issue_band.setObjectName("WizardShellIssueBand")
        outer.addWidget(self._issue_band)

        # ── Content stack ────────────────────────────────────────────
        self._stack = QStackedWidget(self)
        self._stack.setObjectName("WizardShellStack")
        outer.addWidget(self._stack, 1)

        # Pre-populate placeholder widgets so the stack indices line
        # up 1:1 with self._records.
        for record in self._records:
            placeholder = QFrame()
            placeholder.setObjectName("WizardShellStepPlaceholder")
            self._stack.addWidget(placeholder)
            record.widget = placeholder

        # ── Footer ───────────────────────────────────────────────────
        self._footer = QFrame(self)
        self._footer.setObjectName("WizardShellFooter")
        footer_layout = QHBoxLayout(self._footer)
        footer_layout.setContentsMargins(
            spacing.dialog_footer_padding_h,
            spacing.dialog_footer_padding_v,
            spacing.dialog_footer_padding_h,
            spacing.dialog_footer_padding_v,
        )
        footer_layout.setSpacing(spacing.compact_gap)

        self._status_label = QLabel("", self._footer)
        self._status_label.setObjectName("WizardShellStatusLabel")
        footer_layout.addWidget(self._status_label)
        footer_layout.addStretch(1)

        self._cancel_btn = QPushButton(cancel_label, self._footer)
        self._cancel_btn.setObjectName("WizardShellCancelButton")
        self._cancel_btn.clicked.connect(self._on_cancel)
        footer_layout.addWidget(self._cancel_btn)

        self._back_btn = QPushButton(back_label, self._footer)
        self._back_btn.setObjectName("WizardShellBackButton")
        self._back_btn.clicked.connect(self._on_back)
        footer_layout.addWidget(self._back_btn)

        self._primary_btn = QPushButton(primary_label, self._footer)
        self._primary_btn.setObjectName("WizardShellPrimaryButton")
        self._primary_btn.setDefault(True)
        self._primary_btn.clicked.connect(self._on_primary)
        footer_layout.addWidget(self._primary_btn)

        outer.addWidget(self._footer)

        self._primary_label = primary_label
        self._finish_label = finish_label
        self._refresh_buttons()

    # ── Public API: step management ──────────────────────────────────

    def step_ids(self) -> tuple[str, ...]:
        return tuple(r.descriptor.id for r in self._records)

    def current_step_id(self) -> str:
        return self._records[self._current_index].descriptor.id

    def current_step_index(self) -> int:
        return self._current_index

    def is_last_step(self) -> bool:
        return self._current_index == len(self._records) - 1

    def state_map(self) -> dict[str, WizardStepStatus]:
        return {r.descriptor.id: r.status for r in self._records}

    def set_step_widget(self, step_id: str, widget: QWidget) -> None:
        idx = self._index_of(step_id)
        record = self._records[idx]
        # Replace the placeholder/previous widget at the same stack index.
        if record.widget is not None:
            self._stack.removeWidget(record.widget)
            record.widget.deleteLater()
        self._stack.insertWidget(idx, widget)
        record.widget = widget
        if idx == self._current_index:
            self._stack.setCurrentIndex(idx)

    def set_step_status(self, step_id: str, status: WizardStepStatus) -> None:
        record = self._records[self._index_of(step_id)]
        record.status = status
        self._stepper.set_step_state(step_id, _STATUS_TO_STEPPER[status])
        self._refresh_buttons()

    def set_step_issues(
        self, step_id: str, issues: Sequence[ValidationIssue]
    ) -> None:
        record = self._records[self._index_of(step_id)]
        record.issues = list(issues)
        if step_id == self.current_step_id():
            self._render_issue_band()
        # Auto-tag step status so the stepper reflects blocking issues.
        if any(i.severity in ("blocker", "error") for i in issues):
            self.set_step_status(step_id, "issues")
        elif record.status == "issues":
            self.set_step_status(step_id, "active")

    def set_status_text(self, text: str) -> None:
        self._status_label.setText(text)

    # ── Public API: navigation ───────────────────────────────────────

    def advance_step(self, *, mark_complete: bool = True) -> None:
        """Move forward to the next step.

        Hosts call this from their ``next_requested`` slot once the
        current step's data has been validated and saved server-side.
        """
        if mark_complete:
            self.set_step_status(self.current_step_id(), "complete")
        if self._current_index >= len(self._records) - 1:
            return
        self._set_active_index(self._current_index + 1)

    def go_back(self) -> None:
        """Move back one step. Current step is *not* marked complete."""
        if self._current_index <= 0:
            return
        # Demote current to pending if it was active (do not overwrite
        # complete/issues — the user may have already validated it).
        current = self._records[self._current_index]
        if current.status == "active":
            current.status = "pending"
            self._stepper.set_step_state(current.descriptor.id, "pending")
        self._set_active_index(self._current_index - 1)

    def goto_step(self, step_id: str) -> None:
        """Jump to ``step_id`` unconditionally (host-controlled).

        Use after a gate check on the host side.
        """
        idx = self._index_of(step_id)
        self._set_active_index(idx)

    # ── Internal helpers ─────────────────────────────────────────────

    def _index_of(self, step_id: str) -> int:
        for i, r in enumerate(self._records):
            if r.descriptor.id == step_id:
                return i
        raise KeyError(f"Unknown wizard step: {step_id}")

    def _set_active_index(self, idx: int) -> None:
        if not 0 <= idx < len(self._records):
            return
        old_id = self._records[self._current_index].descriptor.id
        # Demote the previously active record if still flagged active.
        prev = self._records[self._current_index]
        if prev.status == "active" and idx != self._current_index:
            prev.status = "pending"
        self._current_index = idx
        new_record = self._records[idx]
        # Don't overwrite a sticky status (complete / issues / skipped).
        if new_record.status == "pending":
            new_record.status = "active"
        # Sync the stepper for the moved cursor.
        for record in self._records:
            self._stepper.set_step_state(
                record.descriptor.id, _STATUS_TO_STEPPER[record.status]
            )
        self._stack.setCurrentIndex(idx)
        self._render_issue_band()
        self._refresh_buttons()
        if old_id != self.current_step_id():
            self.step_changed.emit(self.current_step_id())

    def _render_issue_band(self) -> None:
        record = self._records[self._current_index]
        if record.issues:
            self._issue_band.show_issues(record.issues)
        else:
            self._issue_band.clear()

    def _refresh_buttons(self) -> None:
        is_last = self.is_last_step()
        self._primary_btn.setText(self._finish_label if is_last else self._primary_label)
        self._back_btn.setEnabled(self._current_index > 0)
        # Primary disabled when the current step has blocking issues.
        record = self._records[self._current_index]
        has_blockers = any(
            i.severity in ("blocker", "error") for i in record.issues
        )
        self._primary_btn.setEnabled(not has_blockers)

    def _build_workflow_steps(self) -> list[WorkflowStep]:
        return [
            WorkflowStep(
                key=r.descriptor.id,
                label=r.descriptor.title,
                description=r.descriptor.description,
                state=_STATUS_TO_STEPPER[r.status],
            )
            for r in self._records
        ]

    # ── Slots ────────────────────────────────────────────────────────

    def _on_primary(self) -> None:
        if self.is_last_step():
            self.finish_requested.emit()
        else:
            self.next_requested.emit(self.current_step_id())

    def _on_back(self) -> None:
        self.back_requested.emit(self.current_step_id())

    def _on_cancel(self) -> None:
        self.cancel_requested.emit()

    def _on_stepper_clicked(self, step_id: str) -> None:
        if step_id == self.current_step_id():
            return
        # Adjacent step clicks are forwarded as next/back requests so
        # the host can run its save/validate flow consistently.
        idx = self._index_of(step_id)
        if idx == self._current_index + 1:
            self.next_requested.emit(self.current_step_id())
            return
        if idx == self._current_index - 1:
            self.back_requested.emit(self.current_step_id())
            return
        # Non-adjacent: enforce the gate here.
        gate = self._records[idx].descriptor.gate
        if gate is not None and not gate(self.state_map()):
            return
        self.jump_requested.emit(step_id)


__all__ = [
    "WizardShell",
    "WizardStepDescriptor",
    "WizardStepStatus",
]
