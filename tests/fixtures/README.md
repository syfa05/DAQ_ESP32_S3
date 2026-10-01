# Jeux de test

Fournis par l'utilisateur (démonstrations IFC Builder 2027.a de CYPE). À ne pas redistribuer hors de ce dépôt sans
vérifier leur licence.

| Fichier | Contenu | Utilisé par |
|---|---|---|
| `Bureau.zip` | `Bureau/Bureau.ifc` (IFC4, 46 murs, 5 niveaux) + DWG, glTF… | `tests/test_ifc_real_files.py` (lu directement dans le zip) |
| `Batiment d'habitation.zip` | `Batiment d'habitation.ifc` (IFC4, 112 murs, 6 niveaux, 6,7 Mo) + DWG, glTF, BC3… | idem |
| `dxf/*.dxf` | 5 plans 2D (AutoCAD R2004) extraits des archives RAR : maison, restaurant, bureaux, hôtel | `tests/test_dxf_analyzer.py` |
| `Demo-IFC-Builder-*.rar` | 6 archives RAR5 : projets `.cyp` (format propriétaire, illisible) + 12 plans `.dxf` | source des `dxf/*.dxf` ; **non lues par les tests** |

Les `.dwg`, `.gltf`, `.bc3` et `.cyp` ne sont pas pris en charge par BrikIA.
