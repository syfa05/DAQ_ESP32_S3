"""Configuration de l'application.

Toutes les valeurs se surchargent par variables d'environnement préfixées
``BRIKIA_`` (ou par un fichier ``.env`` dans le répertoire de lancement).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="BRIKIA_", env_file=".env", extra="ignore"
    )

    # --- Réseau -------------------------------------------------------
    # Défaut prudent (poste local). Pour le déploiement en réseau local,
    # définir BRIKIA_HOST=0.0.0.0 ou l'adresse LAN du PC industriel.
    # Ne jamais exposer directement à Internet (voir docs/deploiement.md).
    host: str = "127.0.0.1"
    port: int = 8000

    # Noms d'hôte acceptés dans l'en-tête Host (protège contre le
    # host-header spoofing). "*" = tout accepter ; en production LAN,
    # lister le nom/l'IP du PC, ex. "brikia.usine.local,192.168.1.20".
    allowed_hosts: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["*"])

    # À activer uniquement derrière un reverse proxy local de confiance
    # (HTTPS futur) : uvicorn honorera alors X-Forwarded-*.
    behind_proxy: bool = False

    # --- Cookies de session ------------------------------------------
    # HTTP local : False. HTTPS (reverse proxy) : True, sinon le navigateur
    # ne renverrait pas le cookie... et inversement un cookie non "secure"
    # circulerait en clair. Se règle sans modifier le code.
    cookie_secure: bool = False
    cookie_samesite: Literal["strict", "lax"] = "strict"
    cookie_name: str = "brikia_session"
    session_ttl_hours: int = 12

    # --- Données ------------------------------------------------------
    data_dir: Path = Path("data")
    database_url: str | None = None  # défaut : sqlite dans data_dir

    # --- Fichiers importés -------------------------------------------
    max_upload_mb: int = 50
    allowed_extensions: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [".step", ".stp", ".ifc", ".pdf"]
    )

    # Règles de calepinage temporaires : fichier JSON de surcharges (optionnel).
    layout_rules_file: Path | None = None

    # --- Logs ---------------------------------------------------------
    log_level: str = "INFO"

    @field_validator("allowed_hosts", "allowed_extensions", mode="before")
    @classmethod
    def _split_csv(cls, v: object) -> object:
        # Autorise BRIKIA_ALLOWED_HOSTS=a,b,c en plus du format JSON.
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("["):
                return json.loads(v)
            return [item.strip() for item in v.split(",") if item.strip()]
        return v

    @field_validator("allowed_extensions")
    @classmethod
    def _normalise_ext(cls, v: list[str]) -> list[str]:
        return [e.lower() if e.startswith(".") else f".{e.lower()}" for e in v]

    # --- Chemins dérivés ---------------------------------------------
    @property
    def db_path(self) -> Path:
        return self.data_dir / "brikia.db"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def effective_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{self.db_path.resolve().as_posix()}"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.uploads_dir, self.backups_dir, self.logs_dir):
            d.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
