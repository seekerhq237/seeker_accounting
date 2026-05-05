"""Payroll UI translation scaffold for Phase 11 terminology work.

The app does not yet have a global translation service. This module keeps
payroll strings behind one small boundary so future Qt translator integration
can replace the in-memory catalog without touching business logic.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

_DEFAULT_LOCALE = "en"
_current_locale = _DEFAULT_LOCALE

_TRANSLATIONS: dict[str, dict[str, str]] = {
    "fr": {
        "Dashboard": "Tableau de bord",
        "People": "Personnel",
        "Setup": "Configuration",
        "Statutory": "Statutaire",
        "Reports": "Rapports",
        "Audit": "Audit",
        "Payroll Workbench": "Espace paie",
        "Loading...": "Chargement...",
        "No active company selected": "Aucune entreprise active sélectionnée",
        "Open run": "Cycle ouvert",
        "Last posted": "Dernière comptabilisation",
        "Active employees": "Employés actifs",
        "Statutory due": "Statutaire dû",
        "Payroll run": "Cycle de paie",
        "Payroll runs": "Cycles de paie",
        "Open and recent payroll runs.": "Cycles de paie ouverts et récents.",
        "Payroll runs are unavailable": "Les cycles de paie sont indisponibles",
        "Payroll calculation services are not reachable for this user.": "Les services de calcul de paie ne sont pas accessibles pour cet utilisateur.",
        "Payroll setup is unavailable": "La configuration de paie est indisponible",
        "Payroll setup services are not reachable for this user.": "Les services de configuration de paie ne sont pas accessibles pour cet utilisateur.",
        "Payroll operations services are not reachable for this user.": "Les services d'opérations de paie ne sont pas accessibles pour cet utilisateur.",
        "Payroll reports are unavailable": "Les rapports de paie sont indisponibles",
        "Audit log is unavailable": "Le journal d'audit est indisponible",
        "Payroll audit services are not reachable for this user.": "Les services d'audit de paie ne sont pas accessibles pour cet utilisateur.",
        "Variable input": "Saisie variable",
        "Variable inputs": "Saisies variables",
        "Compensation": "Rémunération",
        "Compensation is unavailable": "La rémunération est indisponible",
        "Compensation name": "Nom de la rémunération",
        "Compensation records and recurring component assignments.": "Rémunérations et affectations récurrentes de composants.",
        "Payroll component": "Composant de paie",
        "Payroll component definition": "Définition du composant de paie",
        "Component assignment": "Affectation de composant",
        "Component assignments": "Affectations de composants",
        "Statutory authority": "Autorité statutaire",
        "Statutory authorities": "Autorités statutaires",
        "Statutory packs are unavailable": "Les packs statutaires sont indisponibles",
        "Statutory packs, remittances, and filing deadlines.": "Packs statutaires, reversements et échéances déclaratives.",
        "Remittance": "Reversement",
        "Remittances": "Reversements",
        "Remittances due": "Reversements dus",
        "Period status, next actions, recent payroll activity.": "Statut de période, prochaines actions et activité récente de paie.",
        "Employees, readiness, hire / terminate / compensation actions.": "Employés, préparation, embauche / départ / rémunération.",
        "Company payroll, payroll components, rules, departments, positions.": "Paie de l'entreprise, composants, règles, départements, postes.",
        "Payslips, summaries, exports.": "Bulletins de paie, synthèses, exports.",
        "Audit trail and validation history.": "Piste d'audit et historique de validation.",
    },
}


def payroll_locale() -> str:
    """Return the active payroll UI locale code."""
    return _current_locale


def set_payroll_locale(locale: str) -> None:
    """Set the active payroll UI locale.

    Unknown locale codes fall back to English so callers can safely pass
    application-level locale values before a full catalog exists.
    """
    global _current_locale
    normalized = (locale or _DEFAULT_LOCALE).split("_")[0].split("-")[0].lower()
    _current_locale = normalized if normalized in _TRANSLATIONS else _DEFAULT_LOCALE


@contextmanager
def payroll_locale_scope(locale: str) -> Iterator[None]:
    """Temporarily switch payroll UI locale inside a small scope."""
    previous = _current_locale
    set_payroll_locale(locale)
    try:
        yield
    finally:
        set_payroll_locale(previous)


def tr(text: str, /, **format_values: object) -> str:
    """Translate a payroll UI string and optionally format named values."""
    translated = _TRANSLATIONS.get(_current_locale, {}).get(text, text)
    if format_values:
        return translated.format(**format_values)
    return translated


translate = tr


__all__ = [
    "payroll_locale",
    "payroll_locale_scope",
    "set_payroll_locale",
    "tr",
    "translate",
]