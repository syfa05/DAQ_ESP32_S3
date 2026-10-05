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
    # Familles de la bibliothèque étendue. DEMI et APPUI sont prélevés par le calcul
    # automatique quand un moule disponible existe ; les autres types (bloc creux, ¾, angle 135°,
    # T, chaînage horizontal, pignon, acrotère, spécial) sont en bibliothèque pour le chiffrage
    # manuel, les plans et la production, sans quantité automatique.
    DEMI = "demi"
    APPUI = "appui"
    CREUX = "creux"
    TROIS_QUARTS = "trois_quarts"
    ANGLE_135 = "angle_135"
    TE = "te"
    CHAINAGE_H = "chainage_h"
    PIGNON = "pignon"
    ACROTERE = "acrotere"
    SPECIAL = "special"


# Catégories prises en compte par le calcul automatique du calepinage.
AUTO_CATEGORIES = ("standard", "angle", "chainage", "linteau", "demi", "appui")


def values(enum_cls: type[StrEnum]) -> list[str]:
    return [e.value for e in enum_cls]
