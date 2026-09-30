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


class ShapeCategory(StrEnum):
    """Fonction d'une forme dans un mur ; le moteur de calepinage raisonne
    par catégorie (jamais par code), donc les codes restent libres."""

    STANDARD = "standard"
    ANGLE = "angle"
    CHAINAGE = "chainage"
    LINTEAU = "linteau"


def values(enum_cls: type[StrEnum]) -> list[str]:
    return [e.value for e in enum_cls]
