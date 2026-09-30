"""Aides de test partagées : parcours projet et horloge simulée."""

from __future__ import annotations

import io
from datetime import UTC, datetime, timedelta

F3 = b"f3-2"  # SHA-256 -> scénario « Maison type F3 »


def new_project(c, csrf, content=F3, name="Villa"):
    r = c.post("/api/projects", headers=csrf, data={"nom": name},
               files={"fichier": ("p.pdf", io.BytesIO(content))})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def to_a_valider(c, csrf, content=F3):
    pid = new_project(c, csrf, content)
    assert c.post(f"/api/projects/{pid}/analyse", headers=csrf).status_code == 200
    assert c.post(f"/api/projects/{pid}/calepinage", headers=csrf).status_code == 200
    return pid


def to_valide(c, csrf, content=F3):
    pid = to_a_valider(c, csrf, content)
    r = c.post(f"/api/projects/{pid}/validation", headers=csrf)
    assert r.status_code == 200, r.text
    return pid


class Clock:
    """Horloge injectable pour le simulateur de production."""

    def __init__(self) -> None:
        self.t = datetime.now(UTC)

    def __call__(self) -> datetime:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += timedelta(seconds=seconds)
