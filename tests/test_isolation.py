"""Isolation des analyseurs natifs : un plantage ou un blocage ne doit jamais toucher le serveur."""

import os
import time
from pathlib import Path

import pytest

from brikia.adapters.analyzers.base import AnalyzerUnavailable, PlanFile
from brikia.adapters.analyzers.dispatch import build_plan_analyzer
from brikia.adapters.analyzers.isolation import run_isolated
from brikia.config import Settings
from brikia.domain.errors import AnalysisFailed

FIXTURES = Path(__file__).parent / "fixtures"


# Cibles exécutées dans le processus fils (fonctions de module : requis par « spawn »).
def ok(x):
    return {"pid": os.getpid(), "x": x}


def domain_error():
    raise AnalysisFailed("Message métier clair.")


def unavailable():
    raise AnalyzerUnavailable("IFC", "ifcopenshell")


def bug():
    raise RuntimeError("secret interne : /etc/passwd")


def crash():
    os._exit(139)   # simule un plantage natif (segfault)


def hang():
    time.sleep(60)


def test_result_comes_back_from_another_process():
    out = run_isolated(ok, (7,), 30)
    assert out["x"] == 7 and out["pid"] != os.getpid()


def test_business_errors_keep_their_message():
    with pytest.raises(AnalysisFailed) as e:
        run_isolated(domain_error, (), 30)
    assert e.value.message == "Message métier clair."


def test_missing_module_is_reported_as_unavailable():
    with pytest.raises(AnalyzerUnavailable) as e:
        run_isolated(unavailable, (), 30)
    assert e.value.package == "ifcopenshell"


def test_unexpected_bug_never_leaks_internal_details():
    with pytest.raises(AnalysisFailed) as e:
        run_isolated(bug, (), 30)
    assert "passwd" not in e.value.message and "échoué" in e.value.message


def test_native_crash_is_contained_and_the_server_survives():
    with pytest.raises(AnalysisFailed) as e:
        run_isolated(crash, (), 30)
    assert "interrompu de façon inattendue" in e.value.message
    assert run_isolated(ok, (1,), 30)["x"] == 1     # le service reste utilisable juste après


def test_hanging_analysis_is_stopped_at_the_deadline():
    started = time.perf_counter()
    with pytest.raises(AnalysisFailed) as e:
        run_isolated(hang, (), 2)
    assert "dépassé 2 secondes" in e.value.message
    assert time.perf_counter() - started < 15


# --- branchement dans l'application ------------------------------------------------------
def plan(path: Path, ext: str) -> PlanFile:
    return PlanFile(path, path.name, ext, path.stat().st_size, "x")


def test_isolated_dispatcher_gives_the_same_geometry_as_in_process():
    pytest.importorskip("ezdxf")
    path = FIXTURES / "dxf" / "Demo - Restaurant (Template F0).dxf"
    isolated = build_plan_analyzer(Settings(_env_file=None, analysis_isolated=True))
    direct = build_plan_analyzer(Settings(_env_file=None, analysis_isolated=False))
    assert isolated._settings is not None and direct._settings is None
    assert isolated.analyse(plan(path, ".dxf")) == direct.analyse(plan(path, ".dxf"))


def test_isolated_dispatcher_reports_bad_files_with_the_analyzers_own_message(tmp_path):
    pytest.importorskip("ifcopenshell")
    bad = tmp_path / "x.ifc"
    bad.write_bytes(b"pas un IFC")
    with pytest.raises(AnalysisFailed) as e:
        build_plan_analyzer(Settings(_env_file=None)).analyse(plan(bad, ".ifc"))
    assert "illisible" in e.value.message


def test_isolation_is_on_by_default_with_a_generous_timeout():
    s = Settings(_env_file=None)
    assert s.analysis_isolated is True and s.analysis_timeout_s == 180
    assert build_plan_analyzer(s)._timeout_s == 180
