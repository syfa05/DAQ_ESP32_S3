"""Contrat ``ProductionGateway`` entre BrikIA et la ligne de production.

Il reprend le contrat futur BrikIA -> Raspberry Pi (``POST /ordres`` et
``GET /etat/{lot_id}``) : un ``RaspberryPiProductionGateway`` pourra remplacer
le simulateur sans modification du domaine.

Sécurité machine : ce contrat ne transporte QUE une recette logique et un
état. Aucune commande de cycle, d'arrêt ou de sécurité : l'automate reste
seul responsable de la sécurité physique.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

STATE_EN_COURS = "en_cours"
STATE_TERMINE = "termine"
STATE_ERREUR = "erreur"


@dataclass(frozen=True)
class OrderPayload:
    lot_id: str
    quantites_par_forme: dict[str, int]  # code de forme -> quantité cible
    envoye_le: datetime | None = None  # horodatage BrikIA de l'ordre (informatif)


@dataclass(frozen=True)
class GatewayReceipt:
    lot_id: str
    accepted: bool
    message: str = ""


@dataclass(frozen=True)
class GatewayStatus:
    lot_id: str
    state: str  # en_cours | termine | erreur
    targets: dict[str, int]
    produced: dict[str, int]
    alarms: tuple[str, ...] = field(default_factory=tuple)  # informatives seulement


class UnknownLot(Exception):
    """La ligne ne connaît pas ce lot (ex. redémarrage du simulateur)."""


class ProductionGateway(Protocol):
    name: str

    def send_order(self, order: OrderPayload) -> GatewayReceipt:
        """Idempotent : renvoyer le même ``lot_id`` ne crée pas un second lot."""

    def get_status(self, lot_id: str) -> GatewayStatus:
        """Lève ``UnknownLot`` si le lot est inconnu."""
