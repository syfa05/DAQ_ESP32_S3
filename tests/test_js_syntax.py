"""Garde-fou : une faute de syntaxe JavaScript casse une page entière sans erreur côté serveur."""

import shutil
import subprocess
from pathlib import Path

import pytest

JS = sorted((Path(__file__).parents[1] / "backend/brikia/static/js").rglob("*.js"))


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js absent")
@pytest.mark.parametrize("path", JS, ids=lambda p: str(p.relative_to(p.parents[3])))
def test_javascript_files_parse(path, tmp_path):
    copy = tmp_path / "m.mjs"  # modules ES : extension .mjs pour que node les analyse comme tels
    copy.write_bytes(path.read_bytes())
    r = subprocess.run(["node", "--check", str(copy)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
