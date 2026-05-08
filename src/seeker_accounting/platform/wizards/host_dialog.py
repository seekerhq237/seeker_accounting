"""Qt host dialog that renders any ``WizardController`` consistently.

Layout (style-guide compliant):

    ┌────────────────────────────────────────────────────────────────────┐
    │ Title bar (window chrome)                                          │
    ├──────────────┬─────────────────────────────────────┬───────────────┤
    │ Step rail    │ Step body (current step.widget)     │ Advisor pane  │
    │ (left, 220)  │  + step header (title + subtitle)   │ (right, 240)  │
    │              │  + inline error strip               │               │
    │              │                                     │               │
    ├──────────────┴─────────────────────────────────────┴───────────────┤
    │ Status strip · "Step X of Y"                                       │
    ├────────────────────────────────────────────────────────────────────┤
    │ [ Cancel ]                              [ Back ] [ Next / Finish ] │
    └────────────────────────────────────────────────────────────────────┘
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QPalette
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.platform.wizards.advisor import AdvisorMessage, AdvisorSeverity
from seeker_accounting.platform.wizards.controller import (
    WizardController,
    WizardLifecycleStatus,
)
from seeker_accounting.platform.wizards.step import WizardStepStatus
from seeker_accounting.shared.ui.layout_constraints import apply_window_size


class WizardHostDialog(QDialog):
    """Generic host dialog for any wizard built on ``WizardController``."""

    def __init__(
        self,
        *,
        controller: WizardController,
        title: str,
        intro: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        apply_window_size(self, "platform.wizards.host.dialog.0")
        self.setObjectName("WizardHostDialog")

        self._controller = controller
        self._intro = intro

        self._build_ui()
        self._render_for_current_step()

    # ── UI construction ──────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Top intro strip ----------------------------------------------------
        if self._intro:
            intro_strip = QFrame(self)
            intro_strip.setObjectName("WizardIntroStrip")
            intro_layout = QHBoxLayout(intro_strip)
            intro_layout.setContentsMargins(20, 10, 20, 10)
            intro_label = QLabel(self._intro, intro_strip)
            intro_label.setObjectName("WizardIntroText")
            intro_label.setWordWrap(True)
            intro_layout.addWidget(intro_label, 1)
            root.addWidget(intro_strip)

        # Three-column body --------------------------------------------------
        body = QWidget(self)
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        root.addWidget(body, 1)

        # Left rail: step list
        self._rail = QListWidget(body)
        self._rail.setObjectName("WizardStepRail")
        self._rail.setFixedWidth(220)
        self._rail.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._rail.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        body_layout.addWidget(self._rail)

        # Center: step body
        center = QWidget(body)
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(20, 16, 20, 16)
        center_layout.setSpacing(10)
        body_layout.addWidget(center, 1)

        self._step_title_label = QLabel("", center)
        self._step_title_label.setObjectName("WizardStepTitle")
        center_layout.addWidget(self._step_title_label)

        self._step_subtitle_label = QLabel("", center)
        self._step_subtitle_label.setObjectName("WizardStepSubtitle")
        self._step_subtitle_label.setWordWrap(True)
        center_layout.addWidget(self._step_subtitle_label)

        self._error_strip = QLabel("", center)
        self._error_strip.setObjectName("WizardErrorStrip")
        self._error_strip.setWordWrap(True)
        self._error_strip.setVisible(False)
        center_layout.addWidget(self._error_strip)

        scroll = QScrollArea(center)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._stack = QStackedWidget(scroll)
        scroll.setWidget(self._stack)
        center_layout.addWidget(scroll, 1)

        # Right: advisor pane
        self._advisor_pane = QFrame(body)
        self._advisor_pane.setObjectName("WizardAdvisorPane")
        self._advisor_pane.setFixedWidth(260)
        advisor_layout = QVBoxLayout(self._advisor_pane)
        advisor_layout.setContentsMargins(14, 16, 14, 16)
        advisor_layout.setSpacing(10)
        advisor_title = QLabel("Assistant", self._advisor_pane)
        advisor_title.setObjectName("WizardAdvisorTitle")
        advisor_layout.addWidget(advisor_title)
        self._advisor_messages_layout = QVBoxLayout()
        self._advisor_messages_layout.setSpacing(8)
        advisor_layout.addLayout(self._advisor_messages_layout)
        advisor_layout.addStretch(1)
        body_layout.addWidget(self._advisor_pane)

        # Status strip -------------------------------------------------------
        status_strip = QFrame(self)
        status_strip.setObjectName("WizardStatusStrip")
        status_strip.setFixedHeight(22)
        status_layout = QHBoxLayout(status_strip)
        status_layout.setContentsMargins(20, 0, 20, 0)
        self._status_label = QLabel("", status_strip)
        self._status_label.setObjectName("WizardStatusText")
        status_layout.addWidget(self._status_label)
        status_layout.addStretch(1)
        root.addWidget(status_strip)

        # Bottom action rail -------------------------------------------------
        action_row = QFrame(self)
        action_row.setObjectName("WizardActionRail")
        action_layout = QHBoxLayout(action_row)
        action_layout.setContentsMargins(20, 12, 20, 12)
        action_layout.setSpacing(8)
        self._cancel_btn = QPushButton("Cancel", action_row)
        self._cancel_btn.clicked.connect(self._on_cancel)
        action_layout.addWidget(self._cancel_btn)
        action_layout.addStretch(1)
        self._back_btn = QPushButton("Back", action_row)
        self._back_btn.clicked.connect(self._on_back)
        action_layout.addWidget(self._back_btn)
        self._next_btn = QPushButton("Next", action_row)
        self._next_btn.setDefault(True)
        self._next_btn.clicked.connect(self._on_next)
        action_layout.addWidget(self._next_btn)
        root.addWidget(action_row)

    # ── Rendering ────────────────────────────────────────────────────────

    def _render_for_current_step(self) -> None:
        controller = self._controller
        step = controller.current_step

        # Build / cache the widget for this step.
        if step.widget is None:
            widget = step.build_widget(self._stack)
            step._set_widget(widget)  # type: ignore[attr-defined]
            self._stack.addWidget(widget)
        try:
            step.load(controller.context, controller.state)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Wizard Error", f"Could not load step:\n\n{exc}")
            return

        self._stack.setCurrentWidget(step.widget)
        self._step_title_label.setText(step.title or step.key)
        self._step_subtitle_label.setText(step.subtitle)
        self._step_subtitle_label.setVisible(bool(step.subtitle))
        self._error_strip.setVisible(False)
        self._error_strip.setText("")

        self._render_rail()
        self._render_advisor()
        self._render_buttons()
        self._render_status()

    def _render_rail(self) -> None:
        self._rail.clear()
        for index, step in enumerate(self._controller.steps):
            prefix_map = {
                WizardStepStatus.COMMITTED: "✓ ",
                WizardStepStatus.VALIDATED: "✓ ",
                WizardStepStatus.SKIPPED: "– ",
                WizardStepStatus.FAILED: "! ",
            }
            prefix = prefix_map.get(step.status, "○ ") if index != self._controller.current_index else "● "
            label = f"{prefix}{step.title or step.key}"
            item = QListWidgetItem(label, self._rail)
            if index == self._controller.current_index:
                font = item.font()
                font.setWeight(QFont.Weight.DemiBold)
                item.setFont(font)
                item.setForeground(QPalette().color(QPalette.ColorRole.Text))
            elif step.status == WizardStepStatus.FAILED:
                item.setData(Qt.ItemDataRole.UserRole, "failed")

    def _render_advisor(self) -> None:
        # Clear existing
        while self._advisor_messages_layout.count():
            item = self._advisor_messages_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        messages: list[AdvisorMessage] = self._controller.evaluate_advisor()
        if not messages:
            empty = QLabel("No suggestions for this step.", self._advisor_pane)
            empty.setObjectName("WizardAdvisorEmpty")
            empty.setWordWrap(True)
            self._advisor_messages_layout.addWidget(empty)
            return

        for msg in messages:
            card = QFrame(self._advisor_pane)
            card.setObjectName("WizardAdvisorCard")
            card.setProperty(
                "advisorSeverity",
                {
                    AdvisorSeverity.BLOCKER: "blocker",
                    AdvisorSeverity.WARNING: "warning",
                    AdvisorSeverity.SUGGESTION: "suggestion",
                    AdvisorSeverity.INFO: "info",
                }.get(msg.severity, "info"),
            )
            card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
            v = QVBoxLayout(card)
            v.setContentsMargins(8, 6, 8, 6)
            v.setSpacing(2)
            t = QLabel(msg.title, card)
            t.setWordWrap(True)
            t.setObjectName("WizardAdvisorCardTitle")
            v.addWidget(t)
            if msg.detail:
                d = QLabel(msg.detail, card)
                d.setWordWrap(True)
                d.setObjectName("WizardAdvisorCardDetail")
                v.addWidget(d)
            if msg.action_label and msg.action is not None:
                btn = QPushButton(msg.action_label, card)
                btn.setObjectName("WizardAdvisorAction")
                btn.clicked.connect(msg.action)  # type: ignore[arg-type]
                v.addWidget(btn)
            self._advisor_messages_layout.addWidget(card)

    def _render_buttons(self) -> None:
        controller = self._controller
        self._back_btn.setEnabled(not controller.is_first)
        if controller.is_last:
            self._next_btn.setText("Finish")
        else:
            self._next_btn.setText("Next")

    def _render_status(self) -> None:
        controller = self._controller
        total = len(controller.steps)
        self._status_label.setText(
            f"Step {controller.current_index + 1} of {total} · {controller.wizard_code}"
        )

    # ── Slots ────────────────────────────────────────────────────────────

    def _on_cancel(self) -> None:
        confirm = QMessageBox.question(
            self,
            "Cancel Wizard",
            "Cancel the wizard? Any uncommitted choices on this step will be lost.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self._controller.cancel()
            self.reject()

    def _on_back(self) -> None:
        self._controller.back()
        self._render_for_current_step()

    def _on_next(self) -> None:
        controller = self._controller
        result = controller.advance()
        if not result.is_valid:
            messages = list(result.blocking_messages)
            for field_label, msg in result.field_errors.items():
                messages.append(f"{field_label}: {msg}")
            self._error_strip.setText("\n".join(messages) or "Please correct the highlighted fields.")
            self._error_strip.setVisible(True)
            return

        if controller.lifecycle is WizardLifecycleStatus.COMMITTED:
            self.accept()
            return

        # If validate moved past last step, run commit_all.
        if controller.is_last and controller.current_step.status in (
            WizardStepStatus.VALIDATED,
            WizardStepStatus.COMMITTED,
        ):
            outcome = controller.commit_all()
            if not outcome.success:
                self._error_strip.setText(outcome.error_message or "Wizard failed during commit.")
                self._error_strip.setVisible(True)
                self._render_rail()
                return
            self.accept()
            return

        self._render_for_current_step()
