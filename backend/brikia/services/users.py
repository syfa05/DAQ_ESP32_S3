"""Administration des comptes : création, activation, mots de passe.

Réservé au chef de projet côté API. Chaque action est tracée dans l'ActionLog
(jamais de mot de passe dans les détails). Les sessions ouvertes d'un compte
sont fermées quand son accès change (désactivation, mot de passe).
"""

from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..domain.enums import Role
from ..domain.errors import Conflict, InvalidCredentials, NotFound, ValidationFailed
from ..models import User, UserSession
from ..security import hash_password, verify_password
from . import audit
from .auth import create_user, validate_password


def list_users(db: Session) -> list[User]:
    return list(db.scalars(select(User).order_by(User.actif.desc(), User.nom, User.id)))


def has_users(db: Session) -> bool:
    return db.scalar(select(func.count(User.id))) > 0


def _get(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise NotFound("Compte introuvable.")
    return user


def _active_chefs(db: Session) -> int:
    return db.scalar(select(func.count(User.id)).where(
        User.role == Role.CHEF_PROJET.value, User.actif.is_(True)))


def add_user(db: Session, actor: User, *, nom: str, login: str, password: str,
             role: Role) -> User:
    user = create_user(db, nom=nom, login=login, password=password, role=role, commit=False)
    audit.record(db, actor, "user.create", "user", user.id,
                 {"login": user.login, "role": user.role})
    db.commit()
    return user


def bootstrap_first_chef(db: Session, *, nom: str, login: str, password: str) -> User:
    """Premier démarrage : crée le premier chef de projet si aucun compte n'existe."""
    if has_users(db):
        raise Conflict("La configuration initiale a déjà été effectuée.")
    user = create_user(db, nom=nom, login=login, password=password,
                       role=Role.CHEF_PROJET, commit=False)
    audit.record(db, user, "user.create", "user", user.id,
                 {"login": user.login, "role": user.role, "initial": True})
    db.commit()
    return user


def set_active(db: Session, actor: User | None, user_id: int, actif: bool) -> User:
    user = _get(db, user_id)
    if user.actif == actif:
        return user
    if not actif:
        if actor is not None and actor.id == user.id:
            raise Conflict("Vous ne pouvez pas désactiver votre propre compte.")
        if user.role == Role.CHEF_PROJET.value and _active_chefs(db) <= 1:
            raise Conflict("Impossible : c'est le dernier chef de projet actif.")
    user.actif = actif
    if not actif:
        db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    audit.record(db, actor, "user.activate" if actif else "user.deactivate", "user",
                 user.id, {"login": user.login})
    db.commit()
    return user


def reset_password(db: Session, actor: User | None, user_id: int, new_password: str) -> User:
    validate_password(new_password)
    user = _get(db, user_id)
    user.password_hash = hash_password(new_password)
    db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    audit.record(db, actor, "user.password_reset", "user", user.id, {"login": user.login})
    db.commit()
    return user


def change_own_password(db: Session, user: User, keep_session_id: int, current: str,
                        new_password: str) -> None:
    if not verify_password(current, user.password_hash):
        raise InvalidCredentials("Le mot de passe actuel est incorrect.")
    validate_password(new_password)
    if new_password == current:
        raise ValidationFailed("Le nouveau mot de passe doit être différent de l'ancien.")
    user.password_hash = hash_password(new_password)
    # Les autres appareils/sessions du compte sont déconnectés.
    db.execute(delete(UserSession).where(
        UserSession.user_id == user.id, UserSession.id != keep_session_id))
    audit.record(db, user, "user.password_change", "user", user.id, {"login": user.login})
    db.commit()
