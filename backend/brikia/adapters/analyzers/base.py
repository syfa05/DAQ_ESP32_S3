from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ...domain.geometry import ProjectGeometry


@dataclass(frozen=True)
class PlanFile:
    """Plan importé, tel que vu par un analyseur."""

    path: Path
    original_name: str
    extension: str
    size: int
    sha256: str


class AnalyzerUnavailable(Exception):
    """Une bibliothèque optionnelle (extra ``phase2``) n'est pas installée.

    Volontairement PAS une ``DomainError`` : c'est un problème d'installation,
    que le répartiteur traduit selon le mode d'analyse (repli simulé signalé,
    ou refus explicite).
    """

    def __init__(self, label: str, package: str) -> None:
        super().__init__(f"{label} : module « {package} » non installé")
        self.label = label
        self.package = package


class PlanAnalyzer(Protocol):
    """Contrat d'analyse de plan.

    Phase 1 : ``SimulatedPlanAnalyzer``. Phase 2 : ``IfcPlanAnalyzer``,
    ``StepPlanAnalyzer`` et ``DxfPlanAnalyzer``, choisis par extension via
    ``ExtensionPlanAnalyzer``, sans modification du pipeline.

    Un analyseur doit lever ``AnalysisFailed`` (message français) si le fichier
    est illisible ou ne contient aucun mur exploitable.
    """

    name: str

    def analyse(self, file: PlanFile) -> ProjectGeometry: ...
