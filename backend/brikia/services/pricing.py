"""Paramètres de chiffrage (modifiables à tout moment) et devis d'un projet."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain.pricing import DEFAULT_RATE, PricingParams, QuoteInput, compute_quote
from ..models import BrickShape, PricingSettings, Project, User
from ..models.base import utcnow
from ..schemas.pricing import TarifsIn
from . import audit, layout


def get_settings(db: Session) -> PricingSettings:
    row = db.get(PricingSettings, 1)
    if row is None:  # base créée sans la migration de données : valeurs par défaut
        row = PricingSettings(id=1, taux_fcfa_par_eur=DEFAULT_RATE, marge_pct=Decimal(20),
                              tva_pct=Decimal(18), frais_fixes_eur=Decimal(0))
        db.add(row)
        db.commit()
    return row


def params(db: Session) -> PricingParams:
    s = get_settings(db)
    return PricingParams(s.taux_fcfa_par_eur, s.marge_pct, s.tva_pct, s.frais_fixes_eur)


def update_settings(db: Session, actor: User, data: TarifsIn) -> PricingSettings:
    row = get_settings(db)
    new = PricingParams(data.taux_fcfa_par_eur, data.marge_pct, data.tva_pct, data.frais_fixes_eur)
    new.validate()
    before = PricingParams(row.taux_fcfa_par_eur, row.marge_pct, row.tva_pct,
                           row.frais_fixes_eur).to_dict()
    after = new.to_dict()
    row.taux_fcfa_par_eur, row.marge_pct = new.taux_fcfa_par_eur, new.marge_pct
    row.tva_pct, row.frais_fixes_eur = new.tva_pct, new.frais_fixes_eur
    row.updated_at, row.updated_by_id = utcnow(), actor.id
    audit.record(db, actor, "pricing.update", "pricing", 1, {
        k: {"avant": before[k], "apres": after[k]} for k in after if before[k] != after[k]})
    db.commit()
    return row


def live_quote(db: Session, project: Project) -> dict:
    """Devis calculé avec les tarifs ACTUELS depuis le dernier calepinage."""
    run = layout.latest_run(db, project)
    bom = layout.build_bom_out(run)
    costs = {s.id: s.cout_unitaire_eur for s in db.scalars(
        select(BrickShape).where(BrickShape.id.in_([ln.shape_id for ln in bom.lignes])))}
    quote = compute_quote(
        [QuoteInput(ln.shape_id, ln.code, ln.nom, ln.categorie, ln.quantite_totale,
                    costs.get(ln.shape_id)) for ln in bom.lignes], params(db))
    quote["fige"] = False
    quote["calcule_le"] = utcnow().isoformat()
    return quote


def quote_for_project(db: Session, project: Project) -> dict:
    """Devis figé si le projet est validé, sinon devis courant (indicatif)."""
    if project.devis:
        return project.devis
    return live_quote(db, project)


def freeze_quote(db: Session, project: Project) -> None:
    """À la validation : fige le devis (sans commit : même transaction que la validation)."""
    quote = live_quote(db, project)
    quote["fige"] = True
    project.devis = quote
