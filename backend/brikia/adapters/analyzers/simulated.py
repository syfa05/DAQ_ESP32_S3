"""Analyse SIMULÉE (phase 1) : le contenu du plan n'est pas lu.

Le scénario est choisi de façon déterministe à partir du SHA-256 du fichier :
même contenu => mêmes murs, quel que soit le nom, l'heure ou la machine.
Les données ci-dessous sont des jeux de démonstration, pas des mesures réelles.
"""

from __future__ import annotations

from ...domain.geometry import OpeningGeometry as O
from ...domain.geometry import ProjectGeometry
from ...domain.geometry import WallGeometry as W
from .base import PlanFile

_FENETRE = ("fenetre", 1200, 1200)
_PORTE = ("porte", 900, 2100)


def _o(spec: tuple[str, int, int]) -> O:
    return O(*spec)


SCENARIOS: dict[str, tuple[W, ...]] = {
    "Maison type F3": (
        W("Façade nord", 10000, 2700, True, (_o(_FENETRE), _o(_FENETRE))),
        W("Façade sud", 10000, 2700, True, (_o(_PORTE), _o(_FENETRE))),
        W("Pignon est", 7000, 2700, True, (O("fenetre", 1000, 1200),)),
        W("Pignon ouest", 7000, 2700, True),
        W("Refend 1", 5000, 2700, False, (_o(_PORTE),)),
        W("Refend 2", 3500, 2700, False, (O("porte", 800, 2100),)),
    ),
    "Local commercial": (
        W("Façade principale", 12000, 3000, True, (O("vitrine", 3000, 2200),)),
        W("Façade arrière", 12000, 3000, True, (O("porte", 1800, 2200),)),
        W("Mur latéral gauche", 8000, 3000, True, (O("fenetre", 1500, 1200),)),
        W("Mur latéral droit", 8000, 3000, True),
    ),
    "Clôture et annexe": (
        W("Clôture nord", 20000, 2000),
        W("Clôture est", 15000, 2000, False, (O("portail", 3000, 2000),)),
        W("Retour d'angle", 4000, 2000, True),
    ),
}

_NAMES = tuple(SCENARIOS)


class SimulatedPlanAnalyzer:
    name = "simulated"

    def analyse(self, file: PlanFile) -> ProjectGeometry:
        index = int(file.sha256[:8], 16) % len(_NAMES)
        scenario = _NAMES[index]
        return ProjectGeometry(
            walls=SCENARIOS[scenario],
            source="simulated",
            notes=(
                "Analyse SIMULÉE : le contenu du plan n'a pas été lu.",
                f"Scénario de démonstration : {scenario}",
            ),
        )
