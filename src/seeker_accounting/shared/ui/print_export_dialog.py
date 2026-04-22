"""Unified print/export format selection dialog for Seeker Accounting.

Shown whenever a user clicks "Print" or "Export" in any module.
Presents three format options (PDF, Word, Excel), page size selector,
and orientation selector.  Opens the OS file-save dialog on confirm.

Usage:
    result = PrintExportDialog.show_dialog(parent, document_title="Sales Invoice")
    if result is not None:
        engine.render_pdf(html, result.output_path, page_size=result.page_size, ...)
"""
from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from seeker_accounting.platform.printing.print_data_protocol import (
    PageOrientation,
    PageSize,
    PrintExportResult,
    PrintFormat,
)


# ── Format card ────────────────────────────────────────────────────────────────

class _FormatCard(QFrame):
    """Selectable format card (PDF / Word / Excel)."""

    def __init__(
        self,
        fmt: PrintFormat,
        icon_char: str,
        description: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._fmt = fmt
        self._selected = False

        self.setObjectName("PrintFormatCard")
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFixedSize(148, 100)
        self.setFrameShape(QFrame.Shape.StyledPanel)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 14, 12, 10)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_lbl = QLabel(icon_char, self)
        icon_lbl.setObjectName("PrintFormatIcon")
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        name_lbl = QLabel(fmt.label, self)
        name_lbl.setObjectName("PrintFormatName")
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_lbl.setWordWrap(False)

        desc_lbl = QLabel(description, self)
        desc_lbl.setObjectName("PrintFormatDesc")
        desc_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc_lbl.setWordWrap(True)

        layout.addWidget(icon_lbl)
        layout.addWidget(name_lbl)
        layout.addWidget(desc_lbl)

        self._update_style()

    @property
    def format(self) -> PrintFormat:
        return self._fmt

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self._update_style()

    def _update_style(self) -> None:
        if self._selected:
            self.setProperty("selected", "true")
        else:
            self.setProperty("selected", "false")
        # Force QSS refresh
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            # Notify parent dialog via callback set during construction
            if hasattr(self, "_on_click"):
                self._on_click(self)
        super().mousePressEvent(event)


# ── Main dialog ────────────────────────────────────────────────────────────────

class PrintExportDialog(QDialog):
    """Print/export format selector dialog.

    Shows format cards (PDF / Word / Excel), page size radio buttons,
    and orientation radio buttons.  On confirm opens the OS file-save
    dialog and returns a ``PrintExportResult``.
    """

    _CARD_DEFS: list[tuple[PrintFormat, str, str]] = [
        (PrintFormat.PDF,   "⬜",  "Best for printing\nand sharing"),
        (PrintFormat.WORD,  "📄",  "Editable in\nMicrosoft Word"),
        (PrintFormat.EXCEL, "📊",  "Data tables\nin spreadsheet"),
    ]

    _LANDSCAPE_TITLE_MARKERS: tuple[str, ...] = (
        " register",
        "chart of accounts",
        "audit log",
    )

    def __init__(
        self,
        document_title: str,
        *,
        default_format: PrintFormat = PrintFormat.PDF,
        default_page_size: PageSize = PageSize.A4,
        default_orientation: PageOrientation | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._document_title = document_title
        self._selected_format = default_format
        self._result: PrintExportResult | None = None
        resolved_orientation = default_orientation or self._suggest_default_orientation(document_title)

        self.setWindowTitle("Export Document")
        self.setModal(True)
        self.setMinimumWidth(520)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 18)
        root.setSpacing(16)

        root.addWidget(self._build_header_row(document_title))
        root.addWidget(self._build_format_section())
        root.addWidget(self._build_page_options_section(default_page_size, resolved_orientation))
        root.addWidget(self._build_button_box())

        # Initial selection
        self._select_card(default_format)

    # ── Class-level helper ──────────────────────────────────────────────────────

    @classmethod
    def show_dialog(
        cls,
        parent: QWidget | None,
        document_title: str,
        *,
        default_format: PrintFormat = PrintFormat.PDF,
        default_page_size: PageSize = PageSize.A4,
        default_orientation: PageOrientation | None = None,
    ) -> PrintExportResult | None:
        """Show the dialog and return a result, or None if cancelled."""
        dlg = cls(
            document_title,
            default_format=default_format,
            default_page_size=default_page_size,
            default_orientation=default_orientation,
            parent=parent,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            return dlg._result
        return None

    @classmethod
    def _suggest_default_orientation(cls, document_title: str) -> PageOrientation:
        normalized_title = " ".join(document_title.lower().split())
        if any(marker in normalized_title for marker in cls._LANDSCAPE_TITLE_MARKERS):
            return PageOrientation.LANDSCAPE
        return PageOrientation.PORTRAIT

    # ── UI builders ─────────────────────────────────────────────────────────────

    def _build_header_row(self, title: str) -> QWidget:
        frame = QFrame(self)
        frame.setObjectName("PageCard")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(2)

        title_lbl = QLabel("Export Document", frame)
        title_lbl.setObjectName("InfoCardTitle")

        doc_lbl = QLabel(title, frame)
        doc_lbl.setObjectName("FieldLabel")
        doc_lbl.setWordWrap(False)

        layout.addWidget(title_lbl)
        layout.addWidget(doc_lbl)
        return frame

    def _build_format_section(self) -> QWidget:
        frame = QFrame(self)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        section_lbl = QLabel("Select Format", frame)
        section_lbl.setObjectName("SectionLabel")
        layout.addWidget(section_lbl)

        cards_row = QHBoxLayout()
        cards_row.setContentsMargins(0, 0, 0, 0)
        cards_row.setSpacing(10)

        self._cards: dict[PrintFormat, _FormatCard] = {}
        for fmt, icon, desc in self._CARD_DEFS:
            card = _FormatCard(fmt, icon, desc, frame)
            card._on_click = self._handle_card_click  # type: ignore[attr-defined]
            self._cards[fmt] = card
            cards_row.addWidget(card)

        cards_row.addStretch(1)
        layout.addLayout(cards_row)
        return frame

    def _build_page_options_section(
        self,
        default_size: PageSize,
        default_orientation: PageOrientation,
    ) -> QWidget:
        frame = QFrame(self)
        frame.setObjectName("PageCard")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        # ── Page size ──────────────────────────────────────────────────────────
        size_lbl = QLabel("Page Size", frame)
        size_lbl.setObjectName("FieldLabel")
        layout.addWidget(size_lbl)

        size_row = QHBoxLayout()
        size_row.setContentsMargins(0, 0, 0, 0)
        size_row.setSpacing(18)

        self._size_group = QButtonGroup(self)
        self._size_radios: dict[PageSize, QRadioButton] = {}
        for size in (PageSize.A4, PageSize.A5):
            rb = QRadioButton(size.label, frame)
            if size == default_size:
                rb.setChecked(True)
            self._size_group.addButton(rb)
            self._size_radios[size] = rb
            size_row.addWidget(rb)

        size_row.addStretch(1)
        layout.addLayout(size_row)

        size_note = QLabel(
            "Page size applies to PDF and Word. Excel exports are size-agnostic.",
            frame,
        )
        size_note.setObjectName("HelpLabel")
        size_note.setWordWrap(True)
        layout.addWidget(size_note)

        # ── Orientation ────────────────────────────────────────────────────────
        orient_lbl = QLabel("Orientation", frame)
        orient_lbl.setObjectName("FieldLabel")
        layout.addWidget(orient_lbl)

        orient_row = QHBoxLayout()
        orient_row.setContentsMargins(0, 0, 0, 0)
        orient_row.setSpacing(18)

        self._orient_group = QButtonGroup(self)
        self._orient_radios: dict[PageOrientation, QRadioButton] = {}
        for orient in (PageOrientation.PORTRAIT, PageOrientation.LANDSCAPE):
            rb = QRadioButton(orient.label, frame)
            if orient == default_orientation:
                rb.setChecked(True)
            self._orient_group.addButton(rb)
            self._orient_radios[orient] = rb
            orient_row.addWidget(rb)

        orient_row.addStretch(1)
        layout.addLayout(orient_row)

        return frame

    def _build_button_box(self) -> QWidget:
        box = QDialogButtonBox(self)
        cancel_btn = box.addButton(QDialogButtonBox.StandardButton.Cancel)
        cancel_btn.setObjectName("CancelButton")
        export_btn = box.addButton("Export…", QDialogButtonBox.ButtonRole.AcceptRole)
        export_btn.setObjectName("PrimaryButton")
        export_btn.setProperty("variant", "primary")

        box.rejected.connect(self.reject)
        box.accepted.connect(self._handle_export)
        return box

    # ── Interaction handlers ────────────────────────────────────────────────────

    def _handle_card_click(self, card: _FormatCard) -> None:
        self._selected_format = card.format
        self._select_card(card.format)

    def _select_card(self, fmt: PrintFormat) -> None:
        for f, card in self._cards.items():
            card.set_selected(f == fmt)

    def _get_selected_page_size(self) -> PageSize:
        for size, rb in self._size_radios.items():
            if rb.isChecked():
                return size
        return PageSize.A4

    def _get_selected_orientation(self) -> PageOrientation:
        for orient, rb in self._orient_radios.items():
            if rb.isChecked():
                return orient
        return PageOrientation.PORTRAIT

    def _handle_export(self) -> None:
        fmt = self._selected_format
        page_size = self._get_selected_page_size()
        orientation = self._get_selected_orientation()

        # Build default filename from document title
        safe_name = "".join(
            c if c.isalnum() or c in (" ", "-", "_") else "_"
            for c in self._document_title
        ).strip()[:60]
        default_filename = f"{safe_name}.{fmt.file_extension}"

        # Determine initial directory (prefer Desktop, fall back to home)
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        start_dir = desktop if os.path.isdir(desktop) else os.path.expanduser("~")

        output_path, _ = QFileDialog.getSaveFileName(
            self,
            f"Save {fmt.label}",
            os.path.join(start_dir, default_filename),
            fmt.file_filter,
        )
        if not output_path:
            return  # user cancelled the file dialog — keep the format dialog open

        # Ensure correct extension
        if not output_path.lower().endswith(f".{fmt.file_extension}"):
            output_path = f"{output_path}.{fmt.file_extension}"

        self._result = PrintExportResult(
            format=fmt,
            output_path=output_path,
            page_size=page_size,
            orientation=orientation,
        )
        self.accept()
