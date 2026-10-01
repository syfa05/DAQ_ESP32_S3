"""Ligne de production SIMULÉE (phase 1) : aucune machine réelle.

Comportement déterministe : la production avance à cadence constante
(``blocks_per_second``) depuis l'horodatage de l'ordre, forme après forme (une
presse ne fabrique qu'un moule à la fois). L'état est une fonction pure de
(ordre, horloge) : on le teste avec une horloge injectée, et il se
reconstitue après un redémarrage grâce à ``envoye_le``.
"""

from __future__ import annotations

import math
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from ...models.base import utcnow
from .base import (
    STATE_EN_COURS, STATE_ERREUR, STATE_TERMINE, GatewayReceipt, GatewayStatus,
    OrderPayload, UnknownLot,
)


@dataclass
class _Lot:
    targets: dict[str, int]
    start: datetime


class SimulatedProductionGateway:
    name = "simulated"

    def __init__(self, blocks_per_second: float = 40.0, fault_at_percent: int | None = None,
                 clock: Callable[[], datetime] = utcnow) -> None:
        self.blocks_per_second = blocks_per_second
        self.fault_at_percent = fault_at_percent
        self._clock = clock
        self._lots: dict[str, _Lot] = {}
        self._lock = threading.Lock()

    def send_order(self, order: OrderPayload) -> GatewayReceipt:
        targets = dict(order.quantites_par_forme)
        if not targets or sum(targets.values()) <= 0 or any(v < 0 for v in targets.values()):
            return GatewayReceipt(order.lot_id, False, "Ordre vide ou invalide (simulation).")
        with self._lock:
            if order.lot_id in self._lots:
                return GatewayReceipt(order.lot_id, True, "Ordre déjà connu de la ligne simulée.")
            self._lots[order.lot_id] = _Lot(targets, order.envoye_le or self._clock())
        return GatewayReceipt(order.lot_id, True, "Ordre accepté (simulation).")

    def get_status(self, lot_id: str) -> GatewayStatus:
        with self._lock:
            lot = self._lots.get(lot_id)
        if lot is None:
            raise UnknownLot(lot_id)
        total = sum(lot.targets.values())
        elapsed = max(0.0, (self._clock() - lot.start).total_seconds())
        done = min(total, math.floor(self.blocks_per_second * elapsed))
        state, alarms = STATE_EN_COURS, ()
        if self.fault_at_percent is not None:
            fault_at = max(1, total * self.fault_at_percent // 100)
            if fault_at < total and done >= fault_at:
                done, state = fault_at, STATE_ERREUR
                alarms = ("Défaut simulé de la ligne (démonstration).",)
        if state == STATE_EN_COURS and done >= total:
            state = STATE_TERMINE
        produced, remaining = {}, done
        for code, target in lot.targets.items():  # forme après forme
            produced[code] = min(target, remaining)
            remaining -= produced[code]
        return GatewayStatus(lot_id, state, dict(lot.targets), produced, alarms)
