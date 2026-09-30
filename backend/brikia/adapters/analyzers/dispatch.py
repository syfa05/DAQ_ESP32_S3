"""Choix de l'analyseur de plan selon l'extension du fichier et le mode configuré.

Règle de sécurité fonctionnelle : on ne présente JAMAIS une géométrie simulée
comme si elle venait du plan de l'utilisateur. Tout repli sur le simulateur
ajoute un avertissement en tête des notes d'analyse (conservées avec le projet
et affichées dans l'interface).

Un fichier réel illisible ou sans mur n'entraîne PAS de repli simulé : c'est
une erreur claire (``AnalysisFailed``) et le projet reste inchangé. Le repli
ne concerne que l'absence d'un module optionnel ou un format non analysable.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import replace
from typing import Literal

from ...domain.errors import AnalysisFailed
from ...domain.geometry import ProjectGeometry
from .base import AnalyzerUnavailable, PlanAnalyzer, PlanFile
from .simulated import SimulatedPlanAnalyzer

log = logging.getLogger("brikia.analyzers")

Mode = Literal["auto", "real", "simulated"]

# Extension -> libellé du format (messages utilisateur).
FORMAT_LABELS = {".ifc": "IFC", ".step": "STEP", ".stp": "STEP", ".dxf": "DXF", ".pdf": "PDF"}


class ExtensionPlanAnalyzer:
    name = "auto"

    def __init__(self, mode: Mode, factories: dict[str, Callable[[], PlanAnalyzer]],
                 simulated: PlanAnalyzer | None = None) -> None:
        self.mode = mode
        self._factories = {k.lower(): v for k, v in factories.items()}
        self._simulated = simulated or SimulatedPlanAnalyzer()
        self._cache: dict[str, PlanAnalyzer] = {}

    # -- repli simulé, toujours signalé ------------------------------------
    def _simulate(self, file: PlanFile, reason: str | None) -> ProjectGeometry:
        geometry = self._simulated.analyse(file)
        if reason:
            geometry = replace(geometry, notes=(reason, *geometry.notes))
        return geometry

    def _real_analyzer(self, ext: str) -> PlanAnalyzer:
        if ext not in self._cache:
            self._cache[ext] = self._factories[ext]()  # peut lever AnalyzerUnavailable
        return self._cache[ext]

    def analyse(self, file: PlanFile) -> ProjectGeometry:
        ext = file.extension.lower()
        label = FORMAT_LABELS.get(ext, ext.lstrip(".").upper() or "inconnu")

        if self.mode == "simulated":
            return self._simulate(file, None)

        if ext not in self._factories:  # PDF, ou format sans analyseur
            if self.mode == "real":
                raise AnalysisFailed(
                    f"Le format {label} ne peut pas être analysé automatiquement. "
                    "Importez un plan IFC, STEP ou DXF."
                )
            return self._simulate(
                file, f"Format {label} : le contenu n'est pas lu, l'analyse est SIMULÉE. "
                      "Importez un plan IFC, STEP ou DXF pour une analyse réelle.")

        try:
            analyzer = self._real_analyzer(ext)
        except AnalyzerUnavailable as exc:
            log.warning("Analyseur %s indisponible : %s", label, exc)
            if self.mode == "real":
                raise AnalysisFailed(
                    f"La lecture des plans {label} n'est pas disponible sur ce poste : "
                    f"module « {exc.package} » non installé (option « phase2 »)."
                ) from exc
            return self._simulate(
                file, f"Module de lecture {label} non installé (« {exc.package} ») : "
                      "l'analyse est SIMULÉE et ne reflète pas votre plan.")
        return analyzer.analyse(file)


def build_plan_analyzer(settings) -> ExtensionPlanAnalyzer:  # noqa: ANN001
    """Assemble le répartiteur ; les imports lourds sont différés à la 1re utilisation."""

    def ifc() -> PlanAnalyzer:
        from .ifc import IfcPlanAnalyzer
        return IfcPlanAnalyzer()

    def step() -> PlanAnalyzer:
        from .step import StepOptions, StepPlanAnalyzer
        return StepPlanAnalyzer(StepOptions.from_settings(settings))

    def dxf() -> PlanAnalyzer:
        from .dxf import DxfOptions, DxfPlanAnalyzer
        return DxfPlanAnalyzer(DxfOptions.from_settings(settings))

    return ExtensionPlanAnalyzer(
        settings.analyzer_mode,
        {".ifc": ifc, ".step": step, ".stp": step, ".dxf": dxf},
    )
