"""Machine d'états des projets : source unique de vérité des transitions.

Aucune autre partie du code ne doit écrire ``project.status`` directement ;
tout passe par ``services.projects.transition`` qui s'appuie sur ce module.
"""

from __future__ import annotations

from .enums import ProjectStatus as S
from .errors import InvalidTransition

ALLOWED_TRANSITIONS: dict[S, frozenset[S]] = {
    S.A_ANALYSER: frozenset({S.A_OPTIMISER}),
    S.A_OPTIMISER: frozenset({S.A_VALIDER}),
    S.A_VALIDER: frozenset({S.VALIDE}),
    S.VALIDE: frozenset({S.EN_PRODUCTION}),
    S.EN_PRODUCTION: frozenset({S.TERMINE}),
    S.TERMINE: frozenset(),
}

# Un opérateur ne voit que la partie production du pipeline.
OPERATOR_VISIBLE: frozenset[S] = frozenset({S.VALIDE, S.EN_PRODUCTION, S.TERMINE})

# Statuts dans lesquels les métadonnées d'un projet restent modifiables
# (avant validation : après, le projet est figé pour la production).
EDITABLE: frozenset[S] = frozenset({S.A_ANALYSER, S.A_OPTIMISER, S.A_VALIDER})

_LABELS = {
    S.A_ANALYSER: "à analyser", S.A_OPTIMISER: "à optimiser", S.A_VALIDER: "à valider",
    S.VALIDE: "validé", S.EN_PRODUCTION: "en production", S.TERMINE: "terminé",
}


def label(status: S | str) -> str:
    return _LABELS[S(status)]


def ensure_transition(current: S | str, target: S | str) -> None:
    current, target = S(current), S(target)
    if target not in ALLOWED_TRANSITIONS[current]:
        raise InvalidTransition(
            f"Transition impossible : un projet « {label(current)} » ne peut pas "
            f"passer à « {label(target)} »."
        )
