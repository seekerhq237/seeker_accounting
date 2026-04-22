from __future__ import annotations

from sqlalchemy.orm import Session


class ReportingWorkspaceRepository:
    """
    Skeleton repository for reporting data queries.

    No query methods are implemented in Slice 14A.
    Future slices will add GL, trial balance, and financial statement
    query methods against posted journal entry data.
    """

    def __init__(self, session: Session) -> None:
        self._session = session
