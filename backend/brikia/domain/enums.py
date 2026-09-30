"""Énumérations métier (Python pur, sans dépendance framework)."""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    CHEF_PROJET = "chef_projet"
    OPERATEUR = "operateur"


class ProjectStatus(StrEnum):
    A_ANALYSER = "a_analyser"
    A_OPTIMISER = "a_optimiser"
    A_VALIDER = "a_valider"
    VALIDE = "valide"
    EN_PRODUCTION = "en_production"
    TERMINE = "termine"


class OrderStatus(StrEnum):
    EN_COURS = "en_cours"
    TERMINE = "termine"
    ERREUR = "erreur"


def values(enum_cls: type[StrEnum]) -> list[str]:
    return [e.value for e in enum_cls]
