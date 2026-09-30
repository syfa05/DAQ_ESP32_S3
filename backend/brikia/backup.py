"""Sauvegarde / restauration en Python pur (indépendant de Windows/Linux).

Une sauvegarde est une archive zip contenant :
- ``brikia.db``  : copie cohérente de la base (API de sauvegarde SQLite,
  correcte même si l'application tourne) ;
- ``uploads/``   : les plans importés.

La restauration doit se faire application arrêtée ; elle conserve une copie
de sécurité de l'état courant avant d'écraser quoi que ce soit.
"""

from __future__ import annotations

import shutil
import sqlite3
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from .config import Settings


class BackupError(Exception):
    pass


def _stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%d-%H%M%S")


def _unique(path: Path) -> Path:
    if not path.exists():
        return path
    i = 1
    while (cand := path.with_name(f"{path.stem}-{i}{path.suffix}")).exists():
        i += 1
    return cand


def create_backup(settings: Settings, dest: Path | None = None, prefix: str = "brikia") -> Path:
    settings.ensure_dirs()
    if not settings.db_path.exists():
        raise BackupError(f"Base introuvable : {settings.db_path}")
    dest = dest or _unique(settings.backups_dir / f"{prefix}-{_stamp()}.zip")
    with tempfile.TemporaryDirectory() as tmp:
        snap = Path(tmp) / "brikia.db"
        src = sqlite3.connect(settings.db_path)
        dst = sqlite3.connect(snap)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        tmp_zip = dest.with_name(dest.name + ".part")
        with zipfile.ZipFile(tmp_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(snap, "brikia.db")
            if settings.uploads_dir.exists():
                for f in sorted(settings.uploads_dir.rglob("*")):
                    if f.is_file() and f.name != ".gitkeep":
                        zf.write(f, "uploads/" + f.relative_to(settings.uploads_dir).as_posix())
        tmp_zip.replace(dest)  # écriture atomique : jamais d'archive tronquée
    return dest


def restore_backup(settings: Settings, archive: Path) -> Path:
    """Restaure ``archive`` ; retourne le chemin de la sauvegarde de sécurité."""
    if not zipfile.is_zipfile(archive):
        raise BackupError(f"Archive invalide : {archive}")
    with zipfile.ZipFile(archive) as zf:
        names = zf.namelist()
        if "brikia.db" not in names:
            raise BackupError("L'archive ne contient pas brikia.db.")
        for n in names:  # protection contre les chemins malveillants (zip-slip)
            p = Path(n)
            if p.is_absolute() or ".." in p.parts or not (
                n == "brikia.db" or n.startswith("uploads/")
            ):
                raise BackupError(f"Entrée d'archive refusée : {n}")

    safety = None
    if settings.db_path.exists():
        safety = create_backup(settings, prefix="avant-restauration")

    with zipfile.ZipFile(archive) as zf, tempfile.TemporaryDirectory() as tmp:
        zf.extractall(tmp)
        tmp_p = Path(tmp)
        # Les fichiers -wal/-shm de l'ancienne base ne doivent pas survivre.
        for suffix in ("", "-wal", "-shm"):
            Path(str(settings.db_path) + suffix).unlink(missing_ok=True)
        shutil.copy2(tmp_p / "brikia.db", settings.db_path)
        if settings.uploads_dir.exists():
            shutil.rmtree(settings.uploads_dir)
        if (tmp_p / "uploads").exists():
            shutil.copytree(tmp_p / "uploads", settings.uploads_dir)
        else:
            settings.uploads_dir.mkdir(parents=True)
    return safety if safety else archive
