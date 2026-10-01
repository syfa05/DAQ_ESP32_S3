"""Test de fumée de bout en bout d'une installation BrikIA (Windows ou Linux).

    python smoke_test.py <python> <launcher.py> [--plan fichier.dxf]

Démarre le lanceur dans un dossier temporaire (BRIKIA_HOME), puis : santé,
configuration initiale (premier chef), connexion, création d'un opérateur,
import d'un plan DXF ou IFC (analyse RÉELLE attendue) et vérification de la source.
"""

from __future__ import annotations

import http.cookiejar
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> int:
    python, launcher = sys.argv[1], sys.argv[2]
    plan = Path(sys.argv[sys.argv.index("--plan") + 1]) if "--plan" in sys.argv else None
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    home = tempfile.mkdtemp(prefix="brikia-smoke-")
    env = {**os.environ, "BRIKIA_HOME": home, "BRIKIA_PORT": str(port)}
    log = open(Path(home) / "serveur.log", "w", encoding="utf-8")  # noqa: SIM115
    proc = subprocess.Popen([python, launcher, "--no-browser"], env=env, stdout=log,
                            stderr=subprocess.STDOUT)
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    csrf = ""

    def call(method, path, body=None, raw=None, headers=None):
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        h = {"Accept": "application/json", "X-CSRF-Token": csrf, **(headers or {})}
        if body is not None:
            h["Content-Type"] = "application/json"
        req = urllib.request.Request(base + path, data=data, method=method, headers=h)
        try:
            with opener.open(req, timeout=120) as r:
                payload = r.read()
                return r.status, (json.loads(payload) if payload else None)
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"null")

    def check(label, cond, extra=""):
        print(("  OK   " if cond else "  ÉCHEC"), label, extra)
        if not cond:
            raise AssertionError(label)

    try:
        for _ in range(120):
            if proc.poll() is not None:
                raise RuntimeError(f"le serveur s'est arrêté (code {proc.returncode})")
            try:
                if call("GET", "/api/health")[0] == 200:
                    break
            except OSError:
                time.sleep(0.5)
        else:
            raise RuntimeError("le serveur ne répond pas")
        check("santé", True)
        check("page d'installation proposée (aucun compte)",
              opener.open(base + "/connexion").geturl().endswith("/installation"))
        status, out = call("POST", "/api/setup",
                           {"nom": "Chef Test", "login": "chef", "password": "mot-de-passe-1"})
        check("configuration initiale (premier chef)", status == 201, str(status))
        csrf = out["csrf_token"]
        status, out = call("POST", "/api/users", {"nom": "Op", "login": "op1",
                           "password": "mot-de-passe-2", "role": "operateur"})
        check("création d'un opérateur", status == 201, str(status))
        status, users = call("GET", "/api/users")
        check("liste des comptes", status == 200 and len(users) == 2)
        if plan:
            expected = plan.suffix.lower().lstrip(".")
            boundary = uuid.uuid4().hex
            parts = [("nom", "Projet fumée"), ("ville", "Test"), ("architecte", "Test")]
            body = b""
            for k, v in parts:
                body += f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
            body += (f'--{boundary}\r\nContent-Disposition: form-data; name="fichier"; '
                     f'filename="{plan.name}"\r\nContent-Type: application/octet-stream\r\n\r\n').encode()
            body += plan.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
            status, proj = call("POST", "/api/projects", raw=body, headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}"})
            check("import du plan", status in (200, 201), str(status))
            status, proj = call("POST", f"/api/projects/{proj['id']}/analyse")
            check("analyse du plan", status == 200, str(status))
            check("analyse RÉELLE (pas simulée)", proj.get("analysis_source") == expected,
                  str(proj.get("analysis_source")))
        print("\nTest de fumée : SUCCÈS")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"\nTest de fumée : ÉCHEC — {exc}")
        log.flush()
        print((Path(home) / "serveur.log").read_text(encoding="utf-8", errors="replace")[-3000:])
        return 1
    finally:
        proc.terminate()
        try:
            proc.wait(15)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())
