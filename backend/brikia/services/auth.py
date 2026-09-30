"""Authentification : identifiants, sessions serveur, limitation des essais."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..domain.enums import Role
from ..domain.errors import (
    InvalidCredentials, TooManyAttempts, ValidationFailed,
)
from ..models import User, UserSession
from ..models.base import utcnow
from ..security import hash_password, hash_token, new_token, verify_password

log = logging.getLogger("brikia.auth")

MIN_PASSWORD_LENGTH = 8


class LoginThrottle:
    """Limite les essais successifs par identifiant (mémoire du processus).

    Compromis assumé : verrouillage court (fenêtre glissante) pour freiner le
    brute-force sur le réseau local sans bloquer durablement un opérateur.
    """

    def __init__(self, max_failures: int = 5, window_s: int = 60,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.max_failures, self.window_s, self._clock = max_failures, window_s, clock
        self._failures: dict[str, list[float]] = {}

    def _recent(self, key: str) -> list[float]:
        now = self._clock()
        recent = [t for t in self._failures.get(key, []) if now - t < self.window_s]
        self._failures[key] = recent
        return recent

    def check(self, key: str) -> None:
        if len(self._recent(key)) >= self.max_failures:
            raise TooManyAttempts(
                "Trop de tentatives de connexion. Réessayez dans un instant."
            )

    def fail(self, key: str) -> None:
        self._recent(key).append(self._clock())

    def reset(self, key: str) -> None:
        self._failures.pop(key, None)


def create_user(db: Session, *, nom: str, login: str, password: str, role: Role) -> User:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValidationFailed(
            f"Le mot de passe doit contenir au moins {MIN_PASSWORD_LENGTH} caractères."
        )
    user = User(nom=nom, login=login.strip().lower(), password_hash=hash_password(password),
                role=Role(role).value)
    db.add(user)
    db.commit()
    return user


def authenticate(db: Session, throttle: LoginThrottle, login: str, password: str) -> User:
    key = login.strip().lower()
    throttle.check(key)
    user = db.scalar(select(User).where(User.login == key))
    ok = verify_password(password, user.password_hash if user else None)
    if not (ok and user and user.actif):
        throttle.fail(key)
        log.warning("Échec de connexion pour l'identifiant %r", key)
        raise InvalidCredentials("Identifiant ou mot de passe incorrect.")
    throttle.reset(key)
    return user


def open_session(db: Session, user: User, ttl_hours: int) -> tuple[str, UserSession]:
    """Crée une session ; retourne (jeton en clair pour le cookie, session)."""
    db.execute(delete(UserSession).where(UserSession.expires_at < utcnow()))
    token = new_token()
    session = UserSession(
        token_hash=hash_token(token), csrf_token=new_token(), user_id=user.id,
        expires_at=utcnow() + timedelta(hours=ttl_hours),
    )
    db.add(session)
    db.commit()
    log.info("Session ouverte pour %s (%s)", user.login, user.role)
    return token, session


def resolve_session(db: Session, token: str | None) -> UserSession | None:
    if not token:
        return None
    s = db.scalar(select(UserSession).where(UserSession.token_hash == hash_token(token)))
    if s is None:
        return None
    if s.expires_at <= utcnow() or not s.user.actif:
        db.delete(s)
        db.commit()
        return None
    return s


def close_session(db: Session, session: UserSession) -> None:
    db.delete(session)
    db.commit()
