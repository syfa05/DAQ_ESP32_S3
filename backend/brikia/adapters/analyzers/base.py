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


class PlanAnalyzer(Protocol):
    """Contrat d'analyse de plan.

    Phase 1 : ``SimulatedPlanAnalyzer``. Phase 2 : ``StepPlanAnalyzer`` /
    ``IfcPlanAnalyzer`` sans modification du pipeline.
    """

    name: str

    def analyse(self, file: PlanFile) -> ProjectGeometry: ...
