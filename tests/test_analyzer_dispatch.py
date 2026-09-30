"""Répartiteur d'analyseurs : jamais de géométrie simulée présentée comme réelle."""

from pathlib import Path

import pytest

from brikia.adapters.analyzers.base import AnalyzerUnavailable, PlanFile
from brikia.adapters.analyzers.dispatch import ExtensionPlanAnalyzer, build_plan_analyzer
from brikia.config import Settings
from brikia.domain.errors import AnalysisFailed
from brikia.domain.geometry import ProjectGeometry, WallGeometry


def plan(ext: str, content: bytes = b"x") -> PlanFile:
    import hashlib
    return PlanFile(Path(f"plan{ext}"), f"plan{ext}", ext, len(content), hashlib.sha256(content).hexdigest())


class Real:
    name = "real"

    def __init__(self, source="ifc"):
        self.source, self.calls = source, 0

    def analyse(self, file):
        self.calls += 1
        return ProjectGeometry((WallGeometry("M", 3000, 2500),), source=self.source, notes=("ok",))


def missing():
    raise AnalyzerUnavailable("IFC", "ifcopenshell")


def test_real_analyzer_chosen_by_extension_and_cached():
    real = Real()
    built = []
    d = ExtensionPlanAnalyzer("auto", {".ifc": lambda: built.append(1) or real})
    assert d.analyse(plan(".IFC")).source == "ifc"  # extension insensible à la casse
    d.analyse(plan(".ifc"))
    assert real.calls == 2 and built == [1]  # analyseur construit une seule fois


def test_auto_falls_back_to_flagged_simulation_when_module_missing():
    d = ExtensionPlanAnalyzer("auto", {".ifc": missing})
    geo = d.analyse(plan(".ifc"))
    assert geo.source == "simulated"
    assert "SIMULÉE" in geo.notes[0] and "ifcopenshell" in geo.notes[0]  # avertissement en tête


def test_auto_pdf_is_simulated_and_flagged():
    geo = ExtensionPlanAnalyzer("auto", {".ifc": Real}).analyse(plan(".pdf"))
    assert geo.source == "simulated" and "PDF" in geo.notes[0] and "SIMULÉE" in geo.notes[0]


def test_real_mode_refuses_instead_of_simulating():
    d = ExtensionPlanAnalyzer("real", {".ifc": missing})
    with pytest.raises(AnalysisFailed) as e:
        d.analyse(plan(".ifc"))
    assert "n'est pas disponible" in e.value.message and "ifcopenshell" in e.value.message
    with pytest.raises(AnalysisFailed) as e:
        d.analyse(plan(".pdf"))
    assert "PDF" in e.value.message


def test_simulated_mode_is_phase1_behaviour_even_if_real_available():
    real = Real()
    geo = ExtensionPlanAnalyzer("simulated", {".ifc": lambda: real}).analyse(plan(".ifc"))
    assert geo.source == "simulated" and real.calls == 0


def test_unreadable_real_file_is_an_error_not_a_silent_simulation():
    """Un fichier réel corrompu ne doit jamais être remplacé par des murs de démonstration."""
    class Broken:
        name = "broken"

        def analyse(self, file):
            raise AnalysisFailed("Le fichier IFC est illisible.")

    with pytest.raises(AnalysisFailed):
        ExtensionPlanAnalyzer("auto", {".ifc": lambda: Broken()}).analyse(plan(".ifc"))


def test_stp_and_step_share_the_step_analyzer():
    d = build_plan_analyzer(Settings(_env_file=None))
    assert {".ifc", ".step", ".stp", ".dxf"} <= set(d._factories)
    assert d._factories[".step"].__name__ == d._factories[".stp"].__name__


def test_settings_mode_reaches_the_dispatcher():
    assert build_plan_analyzer(Settings(_env_file=None, analyzer_mode="real")).mode == "real"
