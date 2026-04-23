"""Shared background task runner for long operations.

Why this exists
---------------
Long-running work (report aggregation, posting runs, imports) must not run
on the Qt UI thread, or the application visibly freezes. Several feature
modules had grown ad-hoc ``QThread`` usage with subtly different lifetime
rules. This module provides a single disciplined pattern:

    from seeker_accounting.shared.ui.background_task import run_with_progress

    result = run_with_progress(
        parent=self,
        title="Trial Balance",
        message="Aggregating posted journal lines…",
        worker=lambda: service.get_trial_balance(filter_dto),
    )
    if result.cancelled:
        return
    if result.error is not None:
        show_error(self, "Trial Balance", str(result.error))
        return
    render(result.value)

Design rules
------------
- ``worker`` runs on a ``QThreadPool`` thread. It must be thread-safe; the
  services in this codebase are safe because each call opens its own
  ``UnitOfWork`` / session.
- Cancellation is cooperative for workers that accept a ``cancel_token``.
  Workers that do not accept a token simply run to completion; the dialog
  still allows the user to close the modal, but the underlying work
  continues (background) until it returns.
- Results, errors, and cancellation are delivered on the UI thread via
  queued signals. Callers never touch thread synchronization directly.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Generic, TypeVar

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtWidgets import QProgressDialog, QWidget

T = TypeVar("T")


class CancelToken:
    """Cooperative cancel flag passed to workers that support cancellation."""

    def __init__(self) -> None:
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled


@dataclass(frozen=True, slots=True)
class TaskResult(Generic[T]):
    """Outcome of a background task invocation."""

    value: T | None
    error: BaseException | None
    cancelled: bool

    @property
    def is_success(self) -> bool:
        return self.error is None and not self.cancelled


class _WorkerSignals(QObject):
    finished = Signal(object)  # value
    failed = Signal(object)  # exception
    cancelled_finished = Signal()


class _Worker(QRunnable):
    def __init__(
        self,
        callable_: Callable[..., Any],
        cancel_token: CancelToken,
        pass_token: bool,
    ) -> None:
        super().__init__()
        self._callable = callable_
        self._cancel_token = cancel_token
        self._pass_token = pass_token
        self.signals = _WorkerSignals()

    def run(self) -> None:  # noqa: D401 — QRunnable override
        try:
            if self._pass_token:
                value = self._callable(self._cancel_token)
            else:
                value = self._callable()
        except BaseException as exc:  # noqa: BLE001 — surfaced via signal
            self.signals.failed.emit(exc)
            return
        if self._cancel_token.is_cancelled:
            self.signals.cancelled_finished.emit()
            return
        self.signals.finished.emit(value)


def run_with_progress(
    parent: QWidget | None,
    title: str,
    message: str,
    worker: Callable[..., T],
    *,
    pass_cancel_token: bool = False,
    show_after_ms: int = 250,
) -> TaskResult[T]:
    """Run ``worker`` on the shared ``QThreadPool`` and block the UI behind a
    cancellable modal progress dialog until it completes.

    Parameters
    ----------
    parent: Owner widget for the progress dialog.
    title/message: Dialog chrome.
    worker: Callable executed off the UI thread. If ``pass_cancel_token`` is
        True, receives a :class:`CancelToken` as its single argument.
    show_after_ms: Suppress dialog flash for operations that finish quickly.

    Returns
    -------
    TaskResult carrying ``value`` / ``error`` / ``cancelled``.
    """
    from PySide6.QtCore import QEventLoop

    token = CancelToken()
    runnable = _Worker(worker, token, pass_cancel_token)

    dialog = QProgressDialog(message, "Cancel", 0, 0, parent)
    dialog.setWindowTitle(title)
    dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
    dialog.setAutoClose(False)
    dialog.setAutoReset(False)
    dialog.setMinimumDuration(show_after_ms)
    # Indeterminate busy indicator (min == max == 0)
    dialog.setRange(0, 0)

    loop = QEventLoop(parent)

    state: dict[str, Any] = {"value": None, "error": None, "cancelled": False}

    def _on_finished(value: Any) -> None:
        state["value"] = value
        loop.quit()

    def _on_failed(exc: Any) -> None:
        state["error"] = exc
        loop.quit()

    def _on_cancelled() -> None:
        state["cancelled"] = True
        loop.quit()

    runnable.signals.finished.connect(_on_finished, Qt.ConnectionType.QueuedConnection)
    runnable.signals.failed.connect(_on_failed, Qt.ConnectionType.QueuedConnection)
    runnable.signals.cancelled_finished.connect(_on_cancelled, Qt.ConnectionType.QueuedConnection)
    dialog.canceled.connect(token.cancel)

    QThreadPool.globalInstance().start(runnable)

    loop.exec()
    dialog.close()

    return TaskResult(
        value=state["value"],
        error=state["error"],
        cancelled=bool(state["cancelled"]),
    )
