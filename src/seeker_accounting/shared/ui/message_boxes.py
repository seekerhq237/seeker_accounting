from __future__ import annotations

from PySide6.QtWidgets import QMessageBox, QWidget

from seeker_accounting.config.constants import APP_NAME


def show_info(parent: QWidget | None, title: str, message: str) -> None:
    QMessageBox.information(parent, title or APP_NAME, message)


def show_warning(parent: QWidget | None, title: str, message: str) -> None:
    QMessageBox.warning(parent, title or APP_NAME, message)


def show_error(parent: QWidget | None, title: str, message: str) -> None:
    QMessageBox.critical(parent, title or APP_NAME, message)


def show_configuration_error(
    parent: QWidget | None,
    title: str,
    message: str,
    action_label: str,
) -> bool:
    """Show a configuration/prerequisite error with an action button.

    Returns True if the user clicked the action button, False otherwise.
    """
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle(title or APP_NAME)
    box.setText(message)
    action_btn = box.addButton(action_label, QMessageBox.ButtonRole.AcceptRole)
    box.addButton(QMessageBox.StandardButton.Close)
    box.exec()
    return box.clickedButton() == action_btn

