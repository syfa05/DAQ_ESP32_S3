import itertools

import pytest

from brikia.db import session_scope
from brikia.domain.enums import ProjectStatus as S
from brikia.domain.errors import Conflict, InvalidTransition
from brikia.domain.states import ALLOWED_TRANSITIONS, ensure_transition
from brikia.models import Project
from brikia.services.projects import transition

ALLOWED = [
    (S.A_ANALYSER, S.A_OPTIMISER),
    (S.A_OPTIMISER, S.A_VALIDER),
    (S.A_VALIDER, S.VALIDE),
    (S.A_VALIDER, S.A_OPTIMISER),
    (S.VALIDE, S.EN_PRODUCTION),
    (S.EN_PRODUCTION, S.TERMINE),
]


@pytest.mark.parametrize(("src", "dst"), ALLOWED)
def test_allowed_transitions(src, dst):
    ensure_transition(src, dst)


@pytest.mark.parametrize(
    ("src", "dst"), [p for p in itertools.product(S, S) if p not in ALLOWED]
)
def test_every_other_transition_is_refused(src, dst):
    """Matrice complète : 36 paires, seules les 5 du pipeline passent."""
    with pytest.raises(InvalidTransition) as exc:
        ensure_transition(src, dst)
    assert "impossible" in exc.value.message


def test_transition_table_has_exactly_five_edges():
    assert sum(len(v) for v in ALLOWED_TRANSITIONS.values()) == 6


def test_unknown_status_rejected():
    with pytest.raises(ValueError):
        ensure_transition("bidon", S.VALIDE)


# --- service : persistance, horodatages, garde de concurrence ---------------
def _project(status=S.A_ANALYSER):
    with session_scope() as s:
        p = Project(nom="P", status=status.value)
        s.add(p)
        s.flush()
        return p.id


def test_transition_persists_and_sets_timestamps(db):
    pid = _project(S.A_VALIDER)
    with session_scope() as s:
        p = s.get(Project, pid)
        transition(s, p, S.VALIDE)
    with session_scope() as s:
        p = s.get(Project, pid)
        assert p.status == "valide" and p.validated_at is not None and p.completed_at is None
        transition(s, p, S.EN_PRODUCTION)
        transition(s, p, S.TERMINE)
    with session_scope() as s:
        p = s.get(Project, pid)
        assert p.status == "termine" and p.completed_at is not None


def test_forbidden_transition_leaves_project_untouched(db):
    pid = _project(S.A_ANALYSER)
    with session_scope() as s:
        p = s.get(Project, pid)
        with pytest.raises(InvalidTransition):
            transition(s, p, S.VALIDE)
    with session_scope() as s:
        assert s.get(Project, pid).status == "a_analyser"


def test_concurrent_transition_is_detected(db):
    """Deux lecteurs du même statut : seul le premier peut transitionner."""
    pid = _project(S.A_ANALYSER)
    with session_scope() as s1, session_scope() as s2:
        p1, p2 = s1.get(Project, pid), s2.get(Project, pid)
        transition(s1, p1, S.A_OPTIMISER)
        s1.commit()
        with pytest.raises(Conflict):
            transition(s2, p2, S.A_OPTIMISER)
