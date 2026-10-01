"""Chiffrage d'un projet en EUR et en FCFA (Python pur, montants EXACTS en Decimal).

Toutes les valeurs d'entrée sont des ESTIMATIONS modifiables (coût de revient par moule,
marge, TVA, frais fixes, taux de change). Règles :

  prix unitaire (devise) = arrondi( coût EUR × (1 + marge %) × taux , décimales de la devise )
  total ligne            = quantité × prix unitaire arrondi   (la facture se recalcule à la main)
  total HT               = Σ lignes + frais fixes (convertis et arrondis)
  TVA                    = arrondi( total HT × TVA % ) ; TTC = HT + TVA

EUR : 2 décimales ; FCFA : entier (le franc CFA n'a pas de subdivision). Le taux officiel est
fixe : 1 EUR = 655,957 FCFA (XOF et XAF) ; il reste modifiable.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from .errors import ValidationFailed

DEFAULT_RATE = Decimal("655.957")


@dataclass(frozen=True)
class PricingParams:
    taux_fcfa_par_eur: Decimal
    marge_pct: Decimal
    tva_pct: Decimal
    frais_fixes_eur: Decimal

    def validate(self) -> None:
        if self.taux_fcfa_par_eur <= 0:
            raise ValidationFailed("Le taux de change doit être strictement positif.")
        if not (0 <= self.marge_pct <= 1000):
            raise ValidationFailed("La marge doit être comprise entre 0 et 1000 %.")
        if not (0 <= self.tva_pct <= 100):
            raise ValidationFailed("La TVA doit être comprise entre 0 et 100 %.")
        if self.frais_fixes_eur < 0:
            raise ValidationFailed("Les frais fixes ne peuvent pas être négatifs.")

    def to_dict(self) -> dict[str, str]:
        return {"taux_fcfa_par_eur": str(self.taux_fcfa_par_eur), "marge_pct": str(self.marge_pct),
                "tva_pct": str(self.tva_pct), "frais_fixes_eur": str(self.frais_fixes_eur)}


@dataclass(frozen=True)
class QuoteInput:
    shape_id: int
    code: str
    nom: str
    categorie: str
    quantite: int
    cout_unitaire_eur: Decimal | None


def _q(value: Decimal, digits: int) -> Decimal:
    return value.quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP)


def _fmt(value: Decimal, digits: int) -> str:
    return f"{_q(value, digits):.{digits}f}"


def compute_quote(lines: list[QuoteInput], params: PricingParams) -> dict:
    """Devis JSON-sérialisable (montants en chaînes décimales exactes)."""
    params.validate()
    warnings: list[str] = []
    factor = 1 + params.marge_pct / 100
    currencies = {"eur": (Decimal(1), 2), "fcfa": (params.taux_fcfa_par_eur, 0)}
    out_lines: list[dict] = []
    material = {c: Decimal(0) for c in currencies}
    cost_total = Decimal(0)

    for ln in lines:
        if ln.quantite <= 0:
            continue
        row = {"shape_id": ln.shape_id, "code": ln.code, "nom": ln.nom, "categorie": ln.categorie,
               "quantite": ln.quantite, "cout_unitaire_eur": None, "chiffre": False}
        if ln.cout_unitaire_eur is None:
            warnings.append(f"Aucun coût défini pour le moule « {ln.code} » : ligne non chiffrée "
                            "(à renseigner dans la page Tarifs).")
            out_lines.append(row)
            continue
        row["chiffre"] = True
        row["cout_unitaire_eur"] = _fmt(ln.cout_unitaire_eur, 4)
        cost_total += ln.cout_unitaire_eur * ln.quantite
        for cur, (rate, digits) in currencies.items():
            unit = _q(ln.cout_unitaire_eur * factor * rate, digits)
            total = unit * ln.quantite
            row[f"prix_unitaire_{cur}"] = _fmt(unit, digits)
            row[f"total_{cur}"] = _fmt(total, digits)
            material[cur] += total
        out_lines.append(row)

    totals: dict[str, dict[str, str]] = {}
    for cur, (rate, digits) in currencies.items():
        frais = _q(params.frais_fixes_eur * rate, digits)
        ht = material[cur] + frais
        tva = _q(ht * params.tva_pct / 100, digits)
        totals[cur] = {"materiel_ht": _fmt(material[cur], digits), "frais_fixes": _fmt(frais, digits),
                       "total_ht": _fmt(ht, digits), "tva": _fmt(tva, digits),
                       "total_ttc": _fmt(ht + tva, digits)}
    return {"estimatif": True, "parametres": params.to_dict(), "lignes": out_lines,
            "eur": totals["eur"], "fcfa": totals["fcfa"],
            "cout_revient_eur": _fmt(cost_total, 2), "avertissements": warnings}
