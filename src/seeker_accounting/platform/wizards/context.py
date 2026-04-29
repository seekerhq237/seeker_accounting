"""Runtime context handed to each wizard step.

Carries the service registry, the active company id, and the user id so that
steps can call services without reaching for global state. Keeping this in a
single dataclass also makes step unit testing straightforward.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from seeker_accounting.app.dependency.service_registry import ServiceRegistry


@dataclass(slots=True)
class WizardContext:
    """Per-run context provided to every step.

    ``company_id`` may be ``None`` for wizards that *create* the company in
    their first step (e.g. Company Setup Wizard). It is the responsibility of
    the wizard's first step to populate ``company_id`` once known.
    """

    service_registry: "ServiceRegistry"
    company_id: int | None
    user_id: int | None
    wizard_run_id: int | None = None

    def require_company_id(self) -> int:
        if self.company_id is None:
            raise RuntimeError("Wizard step requires an active company but none is set.")
        return self.company_id

    def with_company(self, company_id: int) -> "WizardContext":
        return WizardContext(
            service_registry=self.service_registry,
            company_id=company_id,
            user_id=self.user_id,
            wizard_run_id=self.wizard_run_id,
        )
