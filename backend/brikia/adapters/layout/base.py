from __future__ import annotations

from typing import Protocol, Sequence

from ...domain.layout import BrickShapeInput, LayoutResult, WallInput


class LayoutEngine(Protocol):
    """Contrat de calepinage : remplaçable sans modifier le pipeline.

    Phase 1 : moteur de règles déterministe (``DefaultRuleBasedLayoutEngine``).
    Plus tard : optimiseur, algorithme géométrique, éventuellement IA.
    """

    name: str

    def calculate(self, walls: Sequence[WallInput],
                  brick_shapes: Sequence[BrickShapeInput]) -> LayoutResult: ...
