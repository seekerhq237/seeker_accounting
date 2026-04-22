from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QLabel


def avatar_initials(display_name: str, fallback: str = "?") -> str:
    words = [segment for segment in display_name.strip().split() if segment]
    if not words:
        return fallback
    if len(words) == 1:
        return words[0][:2].upper()
    return f"{words[0][0]}{words[1][0]}".upper()


def circular_avatar_pixmap(image_path: str | Path | None, size: int) -> QPixmap:
    if image_path is None:
        return QPixmap()

    source = QPixmap(str(image_path))
    if source.isNull():
        return QPixmap()

    scaled = source.scaled(
        size,
        size,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )

    x_offset = max((scaled.width() - size) // 2, 0)
    y_offset = max((scaled.height() - size) // 2, 0)
    square = scaled.copy(x_offset, y_offset, size, size)

    masked = QPixmap(size, size)
    masked.fill(Qt.GlobalColor.transparent)

    painter = QPainter(masked)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    clip_path = QPainterPath()
    clip_path.addEllipse(QRectF(0, 0, size, size))
    painter.setClipPath(clip_path)
    painter.drawPixmap(0, 0, square)
    painter.end()
    return masked


def apply_avatar_to_label(
    label: QLabel,
    *,
    display_name: str,
    size: int,
    image_path: str | Path | None = None,
    fallback: str = "?",
) -> bool:
    avatar_pixmap = circular_avatar_pixmap(image_path, size)
    has_image = not avatar_pixmap.isNull()

    if has_image:
        label.setPixmap(avatar_pixmap)
        label.setText("")
    else:
        label.setPixmap(QPixmap())
        label.setText(avatar_initials(display_name, fallback=fallback))

    label.setProperty("avatarMode", "image" if has_image else "fallback")
    label.style().unpolish(label)
    label.style().polish(label)
    return has_image
