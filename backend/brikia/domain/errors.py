"""Erreurs métier (Python pur). Le mapping HTTP est fait dans ``api/errors.py``.

Les messages sont en français et destinés à l'utilisateur final.
"""

from __future__ import annotations


class DomainError(Exception):
    code = "erreur"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class AuthenticationRequired(DomainError):
    code = "non_authentifie"


class InvalidCredentials(DomainError):
    code = "identifiants_invalides"


class TooManyAttempts(DomainError):
    code = "trop_de_tentatives"


class PermissionDenied(DomainError):
    code = "acces_refuse"


class CsrfError(DomainError):
    code = "csrf_invalide"


class NotFound(DomainError):
    code = "introuvable"


class Conflict(DomainError):
    code = "conflit"


class InvalidTransition(Conflict):
    code = "transition_interdite"


class ValidationFailed(DomainError):
    code = "donnees_invalides"
