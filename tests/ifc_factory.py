"""Générateur de petits fichiers IFC4 synthétiques pour les tests (nécessite ifcopenshell + shapely).

Géométrie construite à la main avec l'API bas niveau (``create_entity``) : les tests ne
dépendent pas de l'API haut niveau d'IfcOpenShell, qui évolue d'une version à l'autre.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import ifcopenshell
from shapely.geometry import LineString


@dataclass
class OpeningSpec:
    kind: str = "door"        # door | window | none (ouverture vide)
    offset: float = 1.0       # position le long du PREMIER segment (m, depuis son début)
    width: float = 0.9
    height: float = 2.1
    sill: float = 0.0


@dataclass
class WallSpec:
    name: str = "Mur"
    points: list[tuple[float, float]] = field(default_factory=lambda: [(0.0, 0.0), (5.0, 0.0)])  # axe, m
    height: float = 2.7
    thickness: float = 0.2
    storey: int = 0
    openings: list[OpeningSpec] = field(default_factory=list)
    with_axis: bool = True
    with_body: bool = True
    gross_factor: float | None = None     # Qto GrossSideArea = L_axe × H × facteur (None = pas de Qto)
    origin: tuple[float, float] = (0.0, 0.0)   # placement local du mur (m)
    rotation_deg: float = 0.0


def build(path, walls: list[WallSpec], *, unit: str = "METRE", storeys=(("RDC", 0.0),),
          extra_slab_opening: bool = False) -> None:
    f = ifcopenshell.file(schema="IFC4")
    k = 1000.0 if unit == "MILLIMETRE" else 1.0   # facteur m -> unité du fichier

    def pt(*xs):
        return f.create_entity("IfcCartesianPoint", tuple(float(x) * k for x in xs))

    def dirn(*xs):
        return f.create_entity("IfcDirection", tuple(float(x) for x in xs))

    def placement3d(origin=(0, 0, 0), ref=(1, 0, 0)):
        return f.create_entity("IfcAxis2Placement3D", pt(*origin), dirn(0, 0, 1), dirn(*ref))

    def local(rel_to, **kw):
        return f.create_entity("IfcLocalPlacement", rel_to, placement3d(**kw))

    length_unit = f.create_entity("IfcSIUnit", UnitType="LENGTHUNIT", Name="METRE",
                                  Prefix="MILLI" if unit == "MILLIMETRE" else None)
    area_unit = f.create_entity("IfcSIUnit", UnitType="AREAUNIT", Name="SQUARE_METRE")
    project = f.create_entity("IfcProject", ifcopenshell.guid.new(), Name="Test",
                              UnitsInContext=f.create_entity("IfcUnitAssignment", (length_unit, area_unit)))
    ctx = f.create_entity("IfcGeometricRepresentationContext", ContextType="Model",
                          CoordinateSpaceDimension=3, Precision=1e-5,
                          WorldCoordinateSystem=placement3d())
    project.RepresentationContexts = (ctx,)
    site = f.create_entity("IfcSite", ifcopenshell.guid.new(), Name="Site", ObjectPlacement=local(None))
    building = f.create_entity("IfcBuilding", ifcopenshell.guid.new(), Name="B",
                               ObjectPlacement=local(site.ObjectPlacement))
    f.create_entity("IfcRelAggregates", ifcopenshell.guid.new(), RelatingObject=project, RelatedObjects=(site,))
    f.create_entity("IfcRelAggregates", ifcopenshell.guid.new(), RelatingObject=site, RelatedObjects=(building,))
    levels = []
    for name, elev in storeys:
        s = f.create_entity("IfcBuildingStorey", ifcopenshell.guid.new(), Name=name, Elevation=elev * k,
                            ObjectPlacement=local(building.ObjectPlacement, origin=(0, 0, elev * k / k)))
        levels.append(s)
    f.create_entity("IfcRelAggregates", ifcopenshell.guid.new(), RelatingObject=building, RelatedObjects=tuple(levels))

    def rep(ident, rtype, items):
        return f.create_entity("IfcShapeRepresentation", ctx, ident, rtype, tuple(items))

    def extrusion(polygon_xy, height):
        profile = f.create_entity("IfcArbitraryClosedProfileDef", "AREA",
                                  None, f.create_entity("IfcPolyline", [
                                      f.create_entity("IfcCartesianPoint", (float(x) * k, float(y) * k))
                                      for x, y in polygon_xy]))
        return f.create_entity("IfcExtrudedAreaSolid", profile, placement3d(), dirn(0, 0, 1), float(height) * k)

    by_storey: dict[int, list] = {}
    for w in walls:
        storey = levels[w.storey]
        wall_pl = local(storey.ObjectPlacement, origin=(w.origin[0], w.origin[1], 0),
                        ref=(math.cos(math.radians(w.rotation_deg)), math.sin(math.radians(w.rotation_deg)), 0))
        reps = []
        if w.with_axis:
            reps.append(rep("Axis", "Curve2D", [f.create_entity("IfcPolyline", [
                f.create_entity("IfcCartesianPoint", (float(x) * k, float(y) * k)) for x, y in w.points])]))
        if w.with_body:
            outline = LineString(w.points).buffer(w.thickness / 2, cap_style=2, join_style=2)
            reps.append(rep("Body", "SweptSolid", [extrusion(list(outline.exterior.coords), w.height)]))
        wall = f.create_entity("IfcWall", ifcopenshell.guid.new(), Name=w.name, ObjectPlacement=wall_pl,
                               Representation=f.create_entity("IfcProductDefinitionShape", None, None, tuple(reps)))
        by_storey.setdefault(w.storey, []).append(wall)

        if w.gross_factor is not None:
            axis_len = sum(math.dist(a, b) for a, b in zip(w.points, w.points[1:]))
            qto = f.create_entity("IfcElementQuantity", ifcopenshell.guid.new(), Name="Qto_WallBaseQuantities",
                                  Quantities=(f.create_entity("IfcQuantityArea", "GrossSideArea", None, None,
                                                              axis_len * w.height * w.gross_factor),
                                              f.create_entity("IfcQuantityLength", "Width", None, None, w.thickness * k)))
            f.create_entity("IfcRelDefinesByProperties", ifcopenshell.guid.new(), RelatedObjects=(wall,),
                            RelatingPropertyDefinition=qto)

        (x0, y0), (x1, y1) = w.points[0], w.points[1]
        seg_len = math.dist((x0, y0), (x1, y1))
        ang = math.atan2(y1 - y0, x1 - x0)
        for o in w.openings:
            # L'ouverture est placée dans le repère du mur : origine = début du 1er segment.
            cx, cy = x0 + (o.offset + o.width / 2) * math.cos(ang), y0 + (o.offset + o.width / 2) * math.sin(ang)
            op_pl = f.create_entity("IfcLocalPlacement", wall_pl, f.create_entity(
                "IfcAxis2Placement3D", pt(cx, cy, o.sill), dirn(0, 0, 1), dirn(math.cos(ang), math.sin(ang), 0)))
            box = [(-o.width / 2, -w.thickness), (o.width / 2, -w.thickness),
                   (o.width / 2, w.thickness), (-o.width / 2, w.thickness)]
            opening = f.create_entity("IfcOpeningElement", ifcopenshell.guid.new(), Name="Ouverture",
                                      ObjectPlacement=op_pl, Representation=f.create_entity(
                                          "IfcProductDefinitionShape", None, None, (rep("Body", "SweptSolid", [extrusion(box, o.height)]),)))
            f.create_entity("IfcRelVoidsElement", ifcopenshell.guid.new(), RelatingBuildingElement=wall,
                            RelatedOpeningElement=opening)
            if o.kind in ("door", "window"):
                cls = "IfcDoor" if o.kind == "door" else "IfcWindow"
                filling = f.create_entity(cls, ifcopenshell.guid.new(), Name=f"{cls}-{o.width}x{o.height}",
                                          ObjectPlacement=op_pl, OverallHeight=o.height * k, OverallWidth=o.width * k)
                f.create_entity("IfcRelFillsElement", ifcopenshell.guid.new(), RelatingOpeningElement=opening,
                                RelatedBuildingElement=filling)
                by_storey[w.storey].append(filling)
        _ = seg_len

    if extra_slab_opening:   # trémie de dalle : ne doit JAMAIS compter comme ouverture de mur
        slab = f.create_entity("IfcSlab", ifcopenshell.guid.new(), Name="Dalle", ObjectPlacement=local(levels[0].ObjectPlacement))
        hole = f.create_entity("IfcOpeningElement", ifcopenshell.guid.new(), Name="Trémie",
                               ObjectPlacement=local(levels[0].ObjectPlacement),
                               Representation=f.create_entity("IfcProductDefinitionShape", None, None, (
                                   rep("Body", "SweptSolid", [extrusion([(0, 0), (1, 0), (1, 1), (0, 1)], 0.2)]),)))
        f.create_entity("IfcRelVoidsElement", ifcopenshell.guid.new(), RelatingBuildingElement=slab, RelatedOpeningElement=hole)
        by_storey.setdefault(0, []).append(slab)

    for idx, elements in by_storey.items():
        f.create_entity("IfcRelContainedInSpatialStructure", ifcopenshell.guid.new(),
                        RelatingStructure=levels[idx], RelatedElements=tuple(elements))
    f.write(str(path))
