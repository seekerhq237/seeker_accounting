from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton, QVBoxLayout, QWidget

from seeker_accounting.config.constants import WINDOW_MIN_HEIGHT, WINDOW_MIN_WIDTH
from seeker_accounting.shared.ui.styles.tokens import DEFAULT_TOKENS


class LandingWindow(QMainWindow):
    login_requested = Signal()
    create_organisation_requested = Signal()
    system_admin_requested = Signal()
    license_requested = Signal()
    get_started_requested = Signal()

    def __init__(
        self,
        logo_path: Path,
        version_text: str,
        window_title: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._logo_path = logo_path
        self._version_text = version_text
        self._has_centered_on_screen = False

        self.setWindowTitle(window_title)
        self.setMinimumSize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)
        self.resize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)

        root = QFrame(self)
        root.setObjectName("LandingRoot")

        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(
            DEFAULT_TOKENS.spacing.window_padding,
            DEFAULT_TOKENS.spacing.landing_panel_padding,
            DEFAULT_TOKENS.spacing.window_padding,
            DEFAULT_TOKENS.spacing.landing_footer_padding,
        )
        root_layout.setSpacing(0)
        root_layout.addStretch(5)

        hero_row = QHBoxLayout()
        hero_row.setContentsMargins(0, 0, 0, 0)
        hero_row.addStretch(1)
        hero_row.addWidget(self._build_brand_panel(root), 0, Qt.AlignmentFlag.AlignCenter)
        hero_row.addStretch(1)
        root_layout.addLayout(hero_row)

        root_layout.addStretch(8)

        footer_row = QHBoxLayout()
        footer_row.setContentsMargins(0, 0, 0, 0)
        footer_row.setSpacing(DEFAULT_TOKENS.spacing.landing_panel_gap)

        admin_trigger = self._build_admin_trigger(root)
        footer_row.addWidget(admin_trigger, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)

        license_trigger = self._build_license_trigger(root)
        footer_row.addWidget(license_trigger, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)

        help_trigger = self._build_help_trigger(root)
        footer_row.addWidget(help_trigger, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)

        version_label = QLabel(self._version_text, root)
        version_label.setObjectName("LandingVersionLabel")
        footer_row.addWidget(version_label, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)
        footer_row.addStretch(1)
        footer_row.addWidget(self._build_action_region(root), 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
        root_layout.addLayout(footer_row)
        self.setCentralWidget(root)

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        if self._has_centered_on_screen:
            return

        self._has_centered_on_screen = True
        screen = self.screen()
        if screen is None:
            return

        frame = self.frameGeometry()
        frame.moveCenter(screen.availableGeometry().center())
        self.move(frame.topLeft())

    def _build_brand_panel(self, parent: QWidget) -> QWidget:
        panel = QWidget(parent)
        panel.setObjectName("LandingHeroZone")
        panel.setMaximumWidth(DEFAULT_TOKENS.sizes.landing_hero_max_width)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        logo_label = QLabel(panel)
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_label.setPixmap(self._build_logo_pixmap())
        layout.addWidget(logo_label, 0, Qt.AlignmentFlag.AlignHCenter)

        wordmark = QWidget(panel)
        wordmark_layout = QHBoxLayout(wordmark)
        wordmark_layout.setContentsMargins(0, 0, 0, 0)
        wordmark_layout.setSpacing(10)

        seeker_label = QLabel("Seeker", wordmark)
        seeker_label.setObjectName("LandingWordmarkStrong")
        wordmark_layout.addWidget(seeker_label)

        accounting_label = QLabel("Accounting", wordmark)
        accounting_label.setObjectName("LandingWordmarkSoft")
        wordmark_layout.addWidget(accounting_label)
        layout.addWidget(wordmark, 0, Qt.AlignmentFlag.AlignHCenter)

        tagline = QLabel("Built for Business Clarity.", panel)
        tagline.setObjectName("LandingTagline")
        tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(tagline, 0, Qt.AlignmentFlag.AlignHCenter)
        return panel

    def _build_action_region(self, parent: QWidget) -> QWidget:
        container = QWidget(parent)
        container.setObjectName("LandingActionZone")
        container.setFixedWidth(DEFAULT_TOKENS.sizes.landing_action_card_width)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addStretch(1)

        login_button = QPushButton("LOG IN", container)
        login_button.setObjectName("LandingLoginButton")
        login_button.setProperty("variant", "primary")
        login_button.setCursor(Qt.CursorShape.PointingHandCursor)
        login_button.setDefault(True)
        login_button.setAutoDefault(True)
        login_button.clicked.connect(self.login_requested.emit)
        layout.addWidget(login_button)

        create_organisation_button = QPushButton("Create Organisation", container)
        create_organisation_button.setObjectName("LandingSecondaryAction")
        create_organisation_button.setCursor(Qt.CursorShape.PointingHandCursor)
        create_organisation_button.setFlat(True)
        create_organisation_button.clicked.connect(self.create_organisation_requested.emit)
        layout.addWidget(create_organisation_button, 0, Qt.AlignmentFlag.AlignRight)
        return container

    def _build_admin_trigger(self, parent: QWidget) -> QPushButton:
        btn = QPushButton("\U0001f527", parent)  # wrench emoji
        btn.setObjectName("LandingAdminTrigger")
        btn.setFixedSize(28, 28)
        btn.setFlat(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip("System Administration")
        btn.clicked.connect(self.system_admin_requested.emit)
        return btn

    def _build_license_trigger(self, parent: QWidget) -> QPushButton:
        btn = QPushButton("\U0001f511", parent)  # key emoji
        btn.setObjectName("LandingLicenseTrigger")
        btn.setFixedSize(28, 28)
        btn.setFlat(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip("License Management")
        btn.clicked.connect(self.license_requested.emit)
        return btn

    def _build_help_trigger(self, parent: QWidget) -> QPushButton:
        btn = QPushButton("\u2139\ufe0f", parent)  # ℹ️ info emoji
        btn.setObjectName("LandingHelpTrigger")
        btn.setFixedSize(28, 28)
        btn.setFlat(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip("Get Started Guide")
        btn.clicked.connect(self.get_started_requested.emit)
        return btn

    def _build_logo_pixmap(self) -> QPixmap:
        pixmap = QPixmap(str(self._logo_path))
        if pixmap.isNull():
            return QPixmap()
        return pixmap.scaled(
            DEFAULT_TOKENS.sizes.landing_logo_size,
            DEFAULT_TOKENS.sizes.landing_logo_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
