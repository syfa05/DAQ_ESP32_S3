"""Construit le dossier d'application Windows autonome (Python embarqué inclus).

    python installer/build_windows.py [--profile complet|leger] [--out build/BrikIA]

* complet : lecture réelle IFC + DXF + STEP (≈ 900 Mo installés)
* leger   : IFC + DXF réels ; STEP en analyse simulée signalée (≈ 600 Mo)

Peut s'exécuter sous Windows, Linux ou macOS (les roues Windows sont téléchargées
pour la cible, rien n'est compilé). Nécessite Internet au moment de la
CONSTRUCTION uniquement ; le PC final n'a besoin ni d'Internet ni de Python.
Le dossier produit est ensuite empaqueté par Inno Setup (installer/BrikIA.iss).
"""

from __future__ import annotations

import argparse
import shutil
import struct
import subprocess
import sys
import urllib.request
import zipfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY_VERSION = "3.12.10"
PY_TAG = "312"
PY_URL = f"https://www.python.org/ftp/python/{PY_VERSION}/python-{PY_VERSION}-embed-amd64.zip"
BASE_PACKAGES = ["fastapi", "uvicorn", "sqlalchemy", "alembic", "pydantic-settings", "jinja2",
                 "python-multipart", "argon2-cffi", "ifcopenshell", "ezdxf"]
STEP_PACKAGES = ["cadquery-ocp"]


def make_icon(path: Path) -> None:
    """Icône 64x64 (brique ocre) encodée en PNG dans un .ico — sans dépendance."""
    size = 64
    rows = bytearray()
    for y in range(size):
        rows.append(0)
        for x in range(size):
            border = x < 3 or y < 3 or x >= size - 3 or y >= size - 3
            joint = (y in (31, 32)) or (x in (19, 20) and y < 31) or (x in (43, 44) and y > 32)
            rgba = (92, 54, 20, 255) if border else (236, 226, 208, 255) if joint else (214, 138, 45, 255)
            rows += bytes(rgba)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(bytes(rows), 9)) + chunk(b"IEND", b""))
    ico = struct.pack("<HHH", 0, 1, 1) + struct.pack("<BBBBHHII", size, size, 0, 0, 1, 32, len(png), 22) + png
    path.write_bytes(ico)


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", choices=["complet", "leger"], default="complet")
    ap.add_argument("--out", type=Path, default=ROOT / "build" / "BrikIA")
    ap.add_argument("--python-zip", type=Path, help="Python embarqué déjà téléchargé (sinon téléchargé)")
    args = ap.parse_args()
    out: Path = args.out
    if out.exists():
        shutil.rmtree(out)
    (out / "python").mkdir(parents=True)

    # 1. Python embarqué
    zpath = args.python_zip or ROOT / "build" / f"python-{PY_VERSION}-embed-amd64.zip"
    if not zpath.exists():
        zpath.parent.mkdir(parents=True, exist_ok=True)
        print(f"Téléchargement de {PY_URL}")
        urllib.request.urlretrieve(PY_URL, zpath)  # noqa: S310
    with zipfile.ZipFile(zpath) as z:
        z.extractall(out / "python")
    # Chemins de recherche : remplace le « ._pth » d'origine (relatifs à python/).
    (out / "python" / f"python{PY_TAG}._pth").write_text(
        f"python{PY_TAG}.zip\n.\n..\\site-packages\n..\\app\\backend\nimport site\n", encoding="utf-8")

    # 2. Dépendances (roues Windows, versions figées par constraints.txt)
    packages = BASE_PACKAGES + (STEP_PACKAGES if args.profile == "complet" else [])
    run([sys.executable, "-m", "pip", "install", "--no-input", "--disable-pip-version-check",
         "--target", str(out / "site-packages"), "--platform", "win_amd64",
         "--python-version", f"{PY_TAG[0]}.{PY_TAG[1:]}", "--implementation", "cp",
         "--only-binary=:all:", "-c", str(ROOT / "constraints.txt"), *packages])
    for junk in (out / "site-packages").glob("bin"):
        shutil.rmtree(junk, ignore_errors=True)

    # 3. Application
    app = out / "app"
    shutil.copytree(ROOT / "backend", app / "backend",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.egg-info"))
    shutil.copytree(ROOT / "migrations", app / "migrations",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copy2(ROOT / "alembic.ini", app / "alembic.ini")
    shutil.copy2(ROOT / "installer" / "launcher.py", app / "launcher.py")
    shutil.copy2(ROOT / ".env.example" if (ROOT / ".env.example").exists() else ROOT / "README.md", app)
    make_icon(out / "brikia.ico")
    (out / "PROFIL.txt").write_text(f"{args.profile}\n", encoding="utf-8")
    size = sum(f.stat().st_size for f in out.rglob("*") if f.is_file()) / 1e6
    print(f"\nDossier prêt : {out} ({size:.0f} Mo, profil {args.profile})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
