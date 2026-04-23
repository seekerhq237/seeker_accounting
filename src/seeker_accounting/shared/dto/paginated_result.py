"""Generic paginated-result DTO used by list queries across modules.

A page contains the rows for the current slice plus pagination metadata
needed by the UI to render paging controls without an extra round-trip.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Sequence, TypeVar

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class PaginatedResult(Generic[T]):
    items: Sequence[T]
    total_count: int
    page: int          # 1-based
    page_size: int

    @property
    def page_count(self) -> int:
        if self.page_size <= 0:
            return 1
        if self.total_count <= 0:
            return 1
        return (self.total_count + self.page_size - 1) // self.page_size

    @property
    def has_previous(self) -> bool:
        return self.page > 1

    @property
    def has_next(self) -> bool:
        return self.page < self.page_count

    @property
    def start_index(self) -> int:
        """1-based index of the first row in the current page (0 if empty)."""
        if not self.items:
            return 0
        return (self.page - 1) * self.page_size + 1

    @property
    def end_index(self) -> int:
        """1-based index of the last row in the current page (0 if empty)."""
        if not self.items:
            return 0
        return self.start_index + len(self.items) - 1


DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 1000


def normalize_page(page: int | None) -> int:
    if page is None or page < 1:
        return 1
    return int(page)


def normalize_page_size(page_size: int | None) -> int:
    if page_size is None or page_size < 1:
        return DEFAULT_PAGE_SIZE
    return min(int(page_size), MAX_PAGE_SIZE)
