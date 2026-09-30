"""Stockage des plans importés : ``data/uploads/<project_id>/<uuid><ext>``.

Le nom de fichier fourni par le client n'est jamais utilisé comme chemin :
il est seulement conservé (nettoyé) pour l'affichage.
"""

from __future__ import annotations

import hashlib
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from ..config import Settings
from ..domain.errors import PayloadTooLarge, ValidationFailed

_CHUNK = 1024 * 1024


@dataclass
class StoredFile:
    relative_path: str
    original_name: str
    size: int
    sha256: str

    def absolute(self, settings: Settings) -> Path:
        return settings.uploads_dir / self.relative_path


def clean_display_name(name: str | None) -> str:
    base = re.split(r"[\\/]", name or "")[-1]
    base = re.sub(r"[\x00-\x1f\x7f]", "", base).strip()
    return base[:200] or "plan"


def check_extension(settings: Settings, name: str) -> str:
    ext = Path(name).suffix.lower()
    if ext not in settings.allowed_extensions:
        allowed = ", ".join(settings.allowed_extensions)
        raise ValidationFailed(f"Format de fichier non accepté. Formats autorisés : {allowed}.")
    return ext


def save_upload(settings: Settings, project_id: int, filename: str | None,
                stream: BinaryIO) -> StoredFile:
    """Copie le flux sur disque (écriture atomique, taille plafonnée, SHA-256)."""
    display = clean_display_name(filename)
    ext = check_extension(settings, display)
    target_dir = settings.uploads_dir / str(project_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    final = target_dir / f"{uuid.uuid4().hex}{ext}"
    tmp = final.with_name(final.name + ".part")
    digest, size = hashlib.sha256(), 0
    try:
        with open(tmp, "wb") as out:
            while chunk := stream.read(_CHUNK):
                size += len(chunk)
                if size > settings.max_upload_bytes:
                    raise PayloadTooLarge(
                        f"Fichier trop volumineux (maximum {settings.max_upload_mb} Mo)."
                    )
                digest.update(chunk)
                out.write(chunk)
            out.flush()
            os.fsync(out.fileno())
        if size == 0:
            raise ValidationFailed("Le fichier importé est vide.")
        tmp.replace(final)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return StoredFile(f"{project_id}/{final.name}", display, size, digest.hexdigest())


def delete_stored(settings: Settings, stored: StoredFile) -> None:
    stored.absolute(settings).unlink(missing_ok=True)
