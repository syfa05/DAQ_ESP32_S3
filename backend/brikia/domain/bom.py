"""Nomenclature (BOM) regroupée par forme, construite depuis un calepinage."""

from __future__ import annotations

from dataclasses import dataclass, field

from .enums import ShapeCategory

_RANK = {c.value: i for i, c in enumerate(ShapeCategory)}


@dataclass(frozen=True)
class BomRow:
    wall_id: int
    wall_nom: str
    shape_id: int
    code: str
    nom: str
    produit: str
    categorie: str
    quantity: int


@dataclass
class BomLine:
    shape_id: int
    code: str
    nom: str
    produit: str
    categorie: str
    total: int = 0
    per_wall: list[tuple[int, str, int]] = field(default_factory=list)


def build_bom(rows: list[BomRow]) -> list[BomLine]:
    lines: dict[int, BomLine] = {}
    for r in sorted(rows, key=lambda r: r.wall_id):
        line = lines.setdefault(
            r.shape_id, BomLine(r.shape_id, r.code, r.nom, r.produit, r.categorie))
        line.total += r.quantity
        line.per_wall.append((r.wall_id, r.wall_nom, r.quantity))
    return sorted(lines.values(), key=lambda ln: (_RANK.get(ln.categorie, 99), ln.code))
