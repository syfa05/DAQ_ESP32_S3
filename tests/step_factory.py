"""Générateur de fichiers STEP synthétiques pour les tests (Open CASCADE via OCP).

Les coordonnées sont en millimètres ; ``write(..., unit=...)`` choisit l'unité ÉCRITE dans le fichier.
"""

from __future__ import annotations

from OCP.BRep import BRep_Builder
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_Transform
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.gp import gp_Ax1, gp_Dir, gp_Pln, gp_Pnt, gp_Trsf, gp_Vec
from OCP.Interface import Interface_Static
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
from OCP.TopoDS import TopoDS_Compound


def box(x, y, z, dx, dy, dz):
    return BRepPrimAPI_MakeBox(gp_Pnt(x, y, z), gp_Pnt(x + dx, y + dy, z + dz)).Shape()


def wall(x, y, length, thickness=200, height=2700, z=0, along="x"):
    """Mur rectangulaire d'axe (x, y) : orienté selon X (along='x') ou Y (along='y')."""
    if along == "x":
        return box(x, y - thickness / 2, z, length, thickness, height)
    return box(x - thickness / 2, y, z, thickness, length, height)


def cut(shape, *tools):
    for t in tools:
        shape = BRepAlgoAPI_Cut(shape, t).Shape()
    return shape


def fuse(a, b):
    return BRepAlgoAPI_Fuse(a, b).Shape()


def _transform(shape, trsf):
    return BRepBuilderAPI_Transform(shape, trsf, True).Shape()


def rotate_z(shape, degrees, cx=0.0, cy=0.0):
    t = gp_Trsf()
    t.SetRotation(gp_Ax1(gp_Pnt(cx, cy, 0), gp_Dir(0, 0, 1)), degrees * 3.141592653589793 / 180)
    return _transform(shape, t)


def to_y_up(shape):
    """Fait passer l'axe vertical de Z à Y (rotation de -90° autour de X)."""
    t = gp_Trsf()
    t.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(1, 0, 0)), -3.141592653589793 / 2)
    return _transform(shape, t)


def translate(shape, dx=0.0, dy=0.0, dz=0.0):
    t = gp_Trsf()
    t.SetTranslation(gp_Vec(dx, dy, dz))
    return _transform(shape, t)


def flat_face(size=1000.0):
    return BRepBuilderAPI_MakeFace(gp_Pln(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), 0, size, 0, size).Shape()


def write(path, shapes, unit: str = "MM") -> None:
    builder, compound = BRep_Builder(), TopoDS_Compound()
    builder.MakeCompound(compound)
    for s in shapes:
        builder.Add(compound, s)
    Interface_Static.SetCVal_s("write.step.unit", unit)
    writer = STEPControl_Writer()
    writer.Transfer(compound, STEPControl_AsIs)
    assert writer.Write(str(path)).name.endswith("RetDone")
