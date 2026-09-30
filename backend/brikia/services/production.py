"""Production : lancement (valide -> en_production) et suivi (-> termine).

Le simulateur avance seul (fonction du temps) ; BrikIA rapatrie l'état à
chaque consultation (``refresh_order``). C'est ce rapatriement qui, une fois
la ligne terminée, fait passer l'ordre puis le projet à ``termine``.
"""

from __future__ import annotations

import logging

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session, selectinload

from ..adapters.production.base import (
    STATE_ERREUR, STATE_TERMINE, OrderPayload, ProductionGateway, UnknownLot,
)
from ..domain import states
from ..domain.enums import OrderStatus, ProjectStatus
from ..domain.errors import Conflict, DomainError, GatewayError, NotFound, ValidationFailed
from ..models import Project, ProductionOrder, ProductionOrderLine, User
from ..models.base import utcnow
from ..schemas.production import OrderLineOut, OrderOut
from . import audit, layout, projects

log = logging.getLogger("brikia.production")

_ORDER_OPTIONS = (
    selectinload(ProductionOrder.lines).selectinload(ProductionOrderLine.brick_shape),
    selectinload(ProductionOrder.project),
)


def _payload(order: ProductionOrder) -> OrderPayload:
    return OrderPayload(
        lot_id=order.lot_id,
        quantites_par_forme={ln.brick_shape.code: ln.target for ln in order.lines},
        envoye_le=order.started_at,
    )


def _send(gateway: ProductionGateway, payload: OrderPayload) -> None:
    try:
        receipt = gateway.send_order(payload)
    except DomainError:
        raise
    except Exception as exc:
        log.exception("Échec d'envoi de l'ordre %s à la ligne", payload.lot_id)
        raise GatewayError("La ligne de production n'est pas joignable.") from exc
    if not receipt.accepted:
        raise GatewayError(f"La ligne de production a refusé l'ordre : {receipt.message}")


# ---------------------------------------------------------------- lancement
def start_production(db: Session, gateway: ProductionGateway, user: User,
                     project: Project) -> ProductionOrder:
    status = ProjectStatus(project.status)
    if status == ProjectStatus.EN_PRODUCTION:
        raise Conflict("Une production est déjà en cours pour ce projet.")
    if status in (ProjectStatus.A_ANALYSER, ProjectStatus.A_OPTIMISER, ProjectStatus.A_VALIDER):
        raise Conflict("Ce projet n'est pas validé : la production ne peut pas être lancée.")
    states.ensure_transition(status, ProjectStatus.EN_PRODUCTION)  # ex. projet déjà terminé

    try:
        bom = layout.build_bom_out(layout.latest_run(db, project))
    except NotFound as exc:
        raise Conflict("Ce projet n'a pas de nomenclature.") from exc
    if bom.total_blocs <= 0:
        raise ValidationFailed("La nomenclature est vide : rien à produire.")

    try:
        # Transition gardée en premier : une requête concurrente (double clic)
        # échoue ici ou sur l'index unique « un seul ordre actif par projet ».
        projects.transition(db, project, ProjectStatus.EN_PRODUCTION)
        order = ProductionOrder(project_id=project.id, created_by_id=user.id,
                                started_at=utcnow(), status=OrderStatus.EN_COURS.value)
        order.lines = [ProductionOrderLine(brick_shape_id=ln.shape_id, target=ln.quantite_totale)
                       for ln in bom.lignes]
        db.add(order)
        db.flush()
        db.refresh(order)
        codes = {ln.shape_id: ln.code for ln in bom.lignes}
        # Envoi avant commit : un refus de la ligne annule tout (rien à défaire).
        # Le lot_id rend l'envoi idempotent ; si le commit échouait ensuite,
        # le lot orphelin resterait sans effet côté simulateur.
        _send(gateway, OrderPayload(
            order.lot_id, {codes[ln.brick_shape_id]: ln.target for ln in order.lines},
            order.started_at))
        audit.record(db, user, "production.start", "production_order", order.id, {
            "project_id": project.id, "lot_id": order.lot_id, "total_blocs": bom.total_blocs,
            "quantites": {ln.code: ln.quantite_totale for ln in bom.lignes},
        })
        db.commit()
    except (Conflict, OperationalError, IntegrityError) as exc:
        db.rollback()
        if isinstance(exc, Conflict):
            raise
        log.warning("Lancement concurrent détecté pour le projet %s", project.id)
        raise Conflict("Une production est déjà en cours ou en cours de lancement "
                       "pour ce projet.") from exc
    except BaseException:
        db.rollback()
        raise
    log.info("Production lancée : projet %s, ordre %s (lot %s) par %s",
             project.id, order.id, order.lot_id, user.login)
    return get_order_row(db, order.id)


# ------------------------------------------------------------------- suivi
def get_order_row(db: Session, order_id: int) -> ProductionOrder:
    order = db.scalar(select(ProductionOrder).where(ProductionOrder.id == order_id)
                      .options(*_ORDER_OPTIONS).execution_options(populate_existing=True))
    if order is None:
        raise NotFound("Ordre de production introuvable.")
    return order


def _close(db: Session, order: ProductionOrder, status: OrderStatus, message: str | None) -> None:
    """Fermeture gardée : un seul appelant concurrent peut fermer l'ordre."""
    result = db.execute(
        update(ProductionOrder)
        .where(ProductionOrder.id == order.id, ProductionOrder.status == OrderStatus.EN_COURS.value)
        .values(status=status.value, message=message,
                completed_at=utcnow() if status == OrderStatus.TERMINE else None)
        .execution_options(synchronize_session=False))
    if result.rowcount != 1:
        raise Conflict("Ordre déjà clôturé.")


def refresh_order(db: Session, gateway: ProductionGateway, order: ProductionOrder) -> ProductionOrder:
    if order.status != OrderStatus.EN_COURS.value:
        return order
    try:
        try:
            st = gateway.get_status(order.lot_id)
        except UnknownLot:
            # La ligne a perdu l'ordre (redémarrage) : on le lui renvoie
            # (idempotent) avec son horodatage d'origine, puis on relit.
            _send(gateway, _payload(order))
            st = gateway.get_status(order.lot_id)
    except DomainError:
        raise
    except Exception as exc:
        log.exception("Lecture d'état impossible pour le lot %s", order.lot_id)
        raise GatewayError("L'état de la ligne de production est indisponible.") from exc

    project = order.project
    try:
        for ln in order.lines:  # jamais de régression, jamais au-delà de la cible
            reported = st.produced.get(ln.brick_shape.code, ln.produced)
            ln.produced = min(ln.target, max(ln.produced, reported))
        if st.state == STATE_TERMINE:
            _close(db, order, OrderStatus.TERMINE, None)
            for ln in order.lines:
                ln.produced = ln.target
            projects.transition(db, project, ProjectStatus.TERMINE)
            audit.record(db, None, "production.complete", "production_order", order.id, {
                "project_id": project.id, "total_produit": sum(l.target for l in order.lines)})
        elif st.state == STATE_ERREUR:
            message = "; ".join(st.alarms)[:255] or "Erreur signalée par la ligne."
            _close(db, order, OrderStatus.ERREUR, message)
            audit.record(db, None, "production.error", "production_order", order.id, {
                "project_id": project.id, "message": message})
        db.commit()
    except (Conflict, OperationalError):
        # Un autre lecteur a déjà avancé/clôturé l'ordre : on relit l'état en base.
        db.rollback()
    return get_order_row(db, order.id)


def refresh_active_orders(db: Session, gateway: ProductionGateway) -> None:
    ids = list(db.scalars(select(ProductionOrder.id).where(
        ProductionOrder.status == OrderStatus.EN_COURS.value)))
    for oid in ids:
        try:
            refresh_order(db, gateway, get_order_row(db, oid))
        except GatewayError:
            log.warning("Ordre %s : état de la ligne indisponible", oid)


def list_orders(db: Session, gateway: ProductionGateway) -> list[ProductionOrder]:
    refresh_active_orders(db, gateway)
    return list(db.scalars(select(ProductionOrder).order_by(ProductionOrder.id.desc())
                           .options(*_ORDER_OPTIONS).execution_options(populate_existing=True)))


def latest_order_for_project(db: Session, project: Project) -> ProductionOrder:
    oid = db.scalar(select(ProductionOrder.id).where(ProductionOrder.project_id == project.id)
                    .order_by(ProductionOrder.id.desc()).limit(1))
    if oid is None:
        raise NotFound("Aucune production pour ce projet.")
    return get_order_row(db, oid)


def order_out(order: ProductionOrder) -> OrderOut:
    lignes = [OrderLineOut(shape_id=ln.brick_shape_id, code=ln.brick_shape.code,
                           nom=ln.brick_shape.nom, cible=ln.target, produite=ln.produced)
              for ln in order.lines]
    target, done = sum(l.cible for l in lignes), sum(l.produite for l in lignes)
    return OrderOut(
        id=order.id, lot_id=order.lot_id, project_id=order.project_id,
        project_nom=order.project.nom, status=order.status, started_at=order.started_at,
        completed_at=order.completed_at, lignes=lignes, total_cible=target,
        total_produit=done, progression_pct=(done * 100 // target) if target else 0,
        alarmes=[order.message] if order.message else [])
