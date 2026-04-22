from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReportTileDTO:
    """Definition of a launch tile within a launcher tab."""

    tile_key: str
    title: str
    description: str
    subtitle: str | None = None


@dataclass(frozen=True, slots=True)
class ReportTabDTO:
    """Definition of a top-level tab in the reports workspace."""

    tab_key: str
    label: str
    description: str
    is_launcher: bool = False
    tiles: tuple[ReportTileDTO, ...] = ()


@dataclass(frozen=True, slots=True)
class ReportingWorkspaceDTO:
    """Assembled workspace definition with all tabs."""

    tabs: tuple[ReportTabDTO, ...]
