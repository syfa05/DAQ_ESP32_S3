from datetime import timedelta

import pytest

from brikia.adapters.production.base import OrderPayload, UnknownLot
from brikia.adapters.production.simulated import SimulatedProductionGateway
from helpers import Clock


def gw(rate=1.0, fault=None):
    clock = Clock()
    return SimulatedProductionGateway(rate, fault, clock), clock


def order(lot="L1", **q):
    return OrderPayload(lot, q or {"A": 10, "B": 5})


def test_send_accepts_and_is_idempotent():
    g, _ = gw()
    assert g.send_order(order()).accepted
    again = g.send_order(order())
    assert again.accepted and "déjà connu" in again.message
    assert g.get_status("L1").targets == {"A": 10, "B": 5}


@pytest.mark.parametrize("q", [{}, {"A": 0}, {"A": -1, "B": 5}])
def test_invalid_orders_refused(q):
    g, _ = gw()
    assert not g.send_order(OrderPayload("L", q)).accepted


def test_unknown_lot():
    g, _ = gw()
    with pytest.raises(UnknownLot):
        g.get_status("nope")


def test_progress_is_sequential_by_shape_and_deterministic():
    g, clock = gw(rate=1.0)
    g.send_order(order())
    start = clock.t
    for elapsed, expected, state in [
        (0, {"A": 0, "B": 0}, "en_cours"),
        (4.9, {"A": 4, "B": 0}, "en_cours"),
        (12, {"A": 10, "B": 2}, "en_cours"),
        (15, {"A": 10, "B": 5}, "termine"),
        (999, {"A": 10, "B": 5}, "termine"),
    ]:
        clock.t = start + timedelta(seconds=elapsed)
        st = g.get_status("L1")
        assert (st.produced, st.state) == (expected, state)
        assert g.get_status("L1") == st  # même horloge => même résultat


def test_start_time_comes_from_payload_so_state_survives_restart():
    g1, clock = gw(rate=2.0)
    sent_at = clock.t
    g1.send_order(OrderPayload("L", {"A": 100}, sent_at))
    clock.advance(10)
    g2 = SimulatedProductionGateway(2.0, None, clock)  # « redémarrage » : mémoire perdue
    with pytest.raises(UnknownLot):
        g2.get_status("L")
    g2.send_order(OrderPayload("L", {"A": 100}, sent_at))
    assert g2.get_status("L").produced == {"A": 20}
    assert g2.get_status("L") == g1.get_status("L")


def test_simulated_fault_freezes_progress_and_raises_alarm():
    g, clock = gw(rate=1.0, fault=50)
    g.send_order(OrderPayload("L", {"A": 100}, clock.t))
    clock.advance(30)
    assert g.get_status("L").state == "en_cours"
    clock.advance(500)
    st = g.get_status("L")
    assert st.state == "erreur" and st.produced == {"A": 50} and st.alarms
    assert "simulé" in st.alarms[0]


def test_no_fault_by_default():
    g, clock = gw(rate=1.0)
    g.send_order(OrderPayload("L", {"A": 10}, clock.t))
    clock.advance(100)
    assert g.get_status("L").state == "termine"
