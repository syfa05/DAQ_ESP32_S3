from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

_Rate = Annotated[Decimal, Field(gt=0, le=Decimal("1000000"), max_digits=14, decimal_places=6)]
_Pct = Annotated[Decimal, Field(ge=0, le=1000, max_digits=8, decimal_places=4)]
_Money = Annotated[Decimal, Field(ge=0, le=Decimal("1000000000"), max_digits=14, decimal_places=4)]


class TarifsIn(BaseModel):
    taux_fcfa_par_eur: _Rate
    marge_pct: _Pct
    tva_pct: _Pct
    frais_fixes_eur: _Money


class TarifsOut(TarifsIn):
    model_config = ConfigDict(from_attributes=True)

    updated_at: datetime
