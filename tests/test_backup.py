import sqlite3
import zipfile

import pytest

from brikia.backup import BackupError, create_backup, restore_backup
from brikia.cli import main
from brikia.db import init_db, session_scope
from brikia.models import Project


def _names(db_path):
    con = sqlite3.connect(db_path)
    try:
        return [r[0] for r in con.execute("select nom from projects order by id")]
    finally:
        con.close()


def test_backup_and_restore_roundtrip(settings, db):
    (settings.uploads_dir / "1").mkdir(parents=True)
    (settings.uploads_dir / "1" / "plan.pdf").write_bytes(b"PLAN")
    with session_scope() as s:
        s.add(Project(nom="Avant"))
    archive = create_backup(settings)
    assert archive.exists()
    with zipfile.ZipFile(archive) as zf:
        assert set(zf.namelist()) == {"brikia.db", "uploads/1/plan.pdf"}

    with session_scope() as s:
        s.add(Project(nom="Apres"))
    (settings.uploads_dir / "1" / "plan.pdf").write_bytes(b"MODIFIE")
    db.dispose()

    safety = restore_backup(settings, archive)
    assert safety.exists() and safety != archive
    assert _names(settings.db_path) == ["Avant"]
    assert (settings.uploads_dir / "1" / "plan.pdf").read_bytes() == b"PLAN"
    init_db(settings)


def test_restore_rejects_bad_archives(settings, db, tmp_path):
    with pytest.raises(BackupError):
        restore_backup(settings, tmp_path / "absent.zip")
    evil = tmp_path / "evil.zip"
    with zipfile.ZipFile(evil, "w") as zf:
        zf.writestr("brikia.db", b"x")
        zf.writestr("../evil.txt", b"x")
    with pytest.raises(BackupError):
        restore_backup(settings, evil)
    empty = tmp_path / "nodb.zip"
    with zipfile.ZipFile(empty, "w") as zf:
        zf.writestr("uploads/a", b"x")
    with pytest.raises(BackupError):
        restore_backup(settings, empty)


def test_cli_migrate_backup_restore(settings, capsys):
    assert main(["migrate"]) == 0
    assert settings.db_path.exists()
    assert main(["backup"]) == 0
    archive = next(settings.backups_dir.glob("brikia-*.zip"))
    assert main(["restore", str(archive)]) == 2  # sans --yes : refusé
    assert main(["restore", str(archive), "--yes"]) == 0
