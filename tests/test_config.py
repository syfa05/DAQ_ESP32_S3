from brikia.config import Settings


def _clean(monkeypatch):
    for k in ("HOST", "PORT", "ALLOWED_HOSTS", "COOKIE_SECURE", "DATABASE_URL"):
        monkeypatch.delenv(f"BRIKIA_{k}", raising=False)


def test_defaults_are_local_and_http_cookie(monkeypatch, tmp_path):
    _clean(monkeypatch)
    s = Settings(_env_file=None, data_dir=tmp_path)
    assert s.host == "127.0.0.1"
    assert s.cookie_secure is False
    assert s.max_upload_bytes == 50 * 1024 * 1024
    assert s.allowed_extensions == [".step", ".stp", ".ifc", ".pdf"]


def test_host_and_cookie_configurable_by_env(monkeypatch, tmp_path):
    _clean(monkeypatch)
    monkeypatch.setenv("BRIKIA_HOST", "0.0.0.0")
    monkeypatch.setenv("BRIKIA_COOKIE_SECURE", "true")
    monkeypatch.setenv("BRIKIA_ALLOWED_HOSTS", "brikia.usine.local, 192.168.1.20")
    s = Settings(_env_file=None, data_dir=tmp_path)
    assert s.host == "0.0.0.0"
    assert s.cookie_secure is True
    assert s.allowed_hosts == ["brikia.usine.local", "192.168.1.20"]


def test_paths_derive_from_data_dir(tmp_path):
    s = Settings(_env_file=None, data_dir=tmp_path)
    assert s.db_path == tmp_path / "brikia.db"
    assert s.effective_database_url.startswith("sqlite:///")
    s.ensure_dirs()
    for d in (s.uploads_dir, s.backups_dir, s.logs_dir):
        assert d.is_dir()
