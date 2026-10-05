"""Rapport PDF d'un projet (reportlab, 100 % hors ligne) et fiches de moules en vectoriel.

Polices PDF standard (Helvetica) : seuls les caractères Latin-1/WinAnsi sont garantis ; les
textes saisis sont filtrés pour éviter les carrés vides (``_t``).
"""

from __future__ import annotations

import io
from datetime import datetime
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (
    BaseDocTemplate, Frame, KeepTogether, NextPageTemplate, PageBreak, PageTemplate, Paragraph, Spacer,
    Table, TableStyle,
)

from ...domain.moldplan import SHEET_H, SHEET_W, Prim

OCRE = colors.HexColor("#b0541f")
INK = colors.HexColor("#1d1a14")
GREY = colors.HexColor("#6b645a")


def _t(value: object) -> str:
    """Texte sûr pour Helvetica : remplace ce que WinAnsi ne sait pas afficher."""
    text = str(value if value is not None else "")
    table = {"≈": "~", "→": "->", "≥": ">=", "≤": "<=", "’": "'", "‘": "'", "–": "-", "—": "-",
             " ": " ", " ": " ", "×": "x", "²": "2", "³": "3", "¾": "3/4", "œ": "oe"}
    out = []
    for ch in text:
        ch = table.get(ch, ch)
        try:
            ch.encode("cp1252")
            out.append(ch)
        except UnicodeEncodeError:
            out.append("?")
    return "".join(out)


def _num(value: str | Decimal | int, digits: int = 0) -> str:
    """Format français : espace comme séparateur de milliers, virgule décimale."""
    d = Decimal(str(value))
    return f"{d:,.{digits}f}".replace(",", "\u00a0").replace(".", ",")  # espace insécable (Latin-1)


# --- Dessin d'une fiche de moule sur un canvas reportlab ----------------------------------
_STYLES = {
    "outline": (INK, 0.5, None, None), "hidden": (GREY, 0.3, (1.6, 1.2), None),
    "fill_top": (INK, 0.3, None, colors.HexColor("#efe3c8")),
    "fill_side": (INK, 0.3, None, colors.HexColor("#c9b48a")),
    "fill_front": (INK, 0.3, None, colors.HexColor("#dcc9a0")),
    "dim": (OCRE, 0.25, None, None), "thin": (INK, 0.2, None, None),
}


def draw_prims(c: rl_canvas.Canvas, prims: list[Prim], x: float, y: float, scale: float) -> None:
    """Dessine la fiche (origine haut-gauche, mm) avec son coin bas-gauche en (x, y) points."""
    def X(v: float) -> float:
        return x + v * mm * scale

    def Y(v: float) -> float:
        return y + (SHEET_H - v) * mm * scale

    for p in prims:
        stroke, width, dash, fill = _STYLES.get(p.style, _STYLES["outline"])
        c.saveState()
        c.setStrokeColor(stroke)
        c.setLineWidth(width * mm * scale * 0.9)
        c.setDash(*(d * mm * scale for d in dash)) if dash else c.setDash()
        if fill is not None:
            c.setFillColor(fill)
        if p.kind == "poly":
            path = c.beginPath()
            path.moveTo(X(p.pts[0][0]), Y(p.pts[0][1]))
            for px, py in p.pts[1:]:
                path.lineTo(X(px), Y(py))
            path.close()
            c.drawPath(path, stroke=1, fill=1 if fill is not None else 0)
        elif p.kind == "line":
            c.line(X(p.pts[0][0]), Y(p.pts[0][1]), X(p.pts[-1][0]), Y(p.pts[-1][1]))
        elif p.kind == "circle":
            c.circle(X(p.cx), Y(p.cy), p.r * mm * scale, stroke=1, fill=0)
        elif p.kind == "text":
            c.setFillColor(OCRE if p.style == "dim" else INK)
            c.setFont("Helvetica-Bold" if p.style == "title" else "Helvetica", p.size * 2.83 * scale)
            tx, ty = X(p.cx), Y(p.cy)
            {"middle": c.drawCentredString, "end": c.drawRightString}.get(
                p.anchor, c.drawString)(tx, ty, _t(p.text))
        c.restoreState()


# --- Rapport -------------------------------------------------------------------------------
CAT_COLORS = {
    "standard": "#c0432e", "angle": "#d68a2d", "chainage": "#7c9f6c", "linteau": "#6f93bf",
    "demi": "#d09a82", "appui": "#7c8f9f", "chainage_h": "#5f7a3d", "trois_quarts": "#b97a52",
}


def _lighten(hex_color: str, k: float = 0.55) -> colors.Color:
    c = colors.HexColor(hex_color)
    return colors.Color(c.red + (1 - c.red) * k, c.green + (1 - c.green) * k, c.blue + (1 - c.blue) * k)


from reportlab.platypus.flowables import Flowable  # noqa: E402


class WallElevation(Flowable):
    """Élévation d'un mur assise par assise, à l'échelle, en vectoriel."""

    def __init__(self, detail: dict, shapes: dict[int, dict], avail_w: float, max_h: float) -> None:
        super().__init__()
        self.d, self.shapes = detail, shapes
        gutter = 6 * mm
        self.gutter = gutter
        L, H = detail["longueur_mm"], detail["assises"] * detail["hauteur_assise_mm"]
        self.scale = min((avail_w - gutter) / L, max_h / H)
        self.width, self.height = gutter + L * self.scale, H * self.scale + 4 * mm

    def wrap(self, aw, ah):  # noqa: ANN001
        return self.width, self.height

    def draw(self) -> None:
        c, d, sc, hc = self.canv, self.d, self.scale, self.d["hauteur_assise_mm"]
        n = d["assises"]
        c.setLineWidth(0.15)
        for ci, runs in enumerate(d["courses"]):
            y = (ci) * hc * sc
            for x, shape, plen, count, cut in runs:
                if shape == 0:
                    c.setFillColor(colors.HexColor("#efece4"))
                    c.setStrokeColor(colors.HexColor("#b9b3a6"))
                    c.rect(self.gutter + x * sc, y, plen * sc, hc * sc, stroke=0, fill=1)
                    continue
                cat = self.shapes.get(shape, {}).get("categorie", "standard")
                base = CAT_COLORS.get(cat, "#8a6d5a")
                c.setFillColor(_lighten(base) if cut else colors.HexColor(base))
                c.setStrokeColor(colors.HexColor("#3b2a1f"))
                for i in range(count):
                    c.rect(self.gutter + (x + i * plen) * sc, y, plen * sc, hc * sc, stroke=1, fill=1)
        c.setFillColor(GREY)
        c.setFont("Helvetica", 5)
        for ci in range(0, n, 5):
            c.drawRightString(self.gutter - 1.2 * mm, ci * hc * sc + hc * sc * 0.25, str(ci + 1))
        c.setStrokeColor(OCRE)
        c.setLineWidth(0.4)
        yb = n * hc * sc + 1.6 * mm
        c.line(self.gutter, yb, self.width, yb)
        c.setFillColor(OCRE)
        c.setFont("Helvetica", 6)
        c.drawCentredString((self.gutter + self.width) / 2, yb + 0.6 * mm, f"{d['longueur_mm']} mm")


def build_report(*, project: dict, walls: list[dict], bom: dict | None, quote: dict | None,
                 mold_sheets: list[tuple[str, list[Prim]]], generated_by: str,
                 generated_at: datetime, version: str, elevations: list[dict] | None = None,
                 elevations_omitted: int = 0) -> bytes:
    buf = io.BytesIO()
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Heading1"], fontName="Helvetica-Bold", fontSize=18,
                        textColor=INK, spaceAfter=4)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontName="Helvetica-Bold", fontSize=12.5,
                        textColor=OCRE, spaceBefore=12, spaceAfter=5)
    body = ParagraphStyle("b", parent=ss["BodyText"], fontName="Helvetica", fontSize=9.2, leading=12)
    small = ParagraphStyle("s", parent=body, fontSize=8, leading=10, textColor=GREY)
    warn = ParagraphStyle("w", parent=body, textColor=colors.HexColor("#8a2d12"))

    def footer(canv: rl_canvas.Canvas, doc) -> None:
        canv.saveState()
        canv.setFont("Helvetica", 7.5)
        canv.setFillColor(GREY)
        canv.drawString(15 * mm, 9 * mm, _t(f"BrikIA {version} - rapport du projet « {project['nom']} » - "
                                           f"{generated_at:%d/%m/%Y %H:%M} UTC - {generated_by}"))
        canv.drawRightString(A4[0] - 15 * mm, 9 * mm, f"Page {doc.page}")
        canv.restoreState()

    doc = BaseDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
                          topMargin=15 * mm, bottomMargin=16 * mm,
                          title=_t(f"Rapport - {project['nom']}"), author="BrikIA")
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="f")
    sheet_w, sheet_h = landscape(A4)
    full = Frame(0, 0, sheet_w, sheet_h, leftPadding=0, rightPadding=0, topPadding=0,
                 bottomPadding=0, id="full")

    def sheet_page(canv: rl_canvas.Canvas, doc_) -> None:
        pass  # le contenu est dessiné par la flowable ci-dessous

    doc.addPageTemplates([PageTemplate(id="portrait", frames=[frame], onPage=footer, pagesize=A4),
                          PageTemplate(id="sheet", frames=[full], onPage=sheet_page,
                                       pagesize=landscape(A4))])

    from reportlab.platypus.flowables import Flowable

    class MoldSheet(Flowable):
        def __init__(self, prims: list[Prim]) -> None:
            super().__init__()
            self.prims = prims
            self.width, self.height = sheet_w, sheet_h

        def wrap(self, aw, ah):  # noqa: ANN001
            return sheet_w, sheet_h

        def draw(self) -> None:
            scale = min(sheet_w / (SHEET_W * mm), sheet_h / (SHEET_H * mm))
            draw_prims(self.canv, self.prims, 0, 0, scale)

    S: list = []
    S.append(Paragraph(_t("Rapport général du projet"), h1))
    S.append(Paragraph(_t(project["nom"]), ParagraphStyle("t", parent=h1, fontSize=14, textColor=OCRE)))
    meta = [["Ville", project.get("ville") or "-", "Architecte", project.get("architecte") or "-"],
            ["Statut", project["statut"], "Créé le", project["cree_le"]],
            ["Plan source", project.get("plan") or "-", "Validé le", project.get("valide_le") or "-"]]
    t = Table([[_t(c) for c in row] for row in meta], colWidths=[24 * mm, 66 * mm, 24 * mm, 66 * mm])
    t.setStyle(TableStyle([("FONT", (0, 0), (-1, -1), "Helvetica", 9),
                           ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 9),
                           ("FONT", (2, 0), (2, -1), "Helvetica-Bold", 9),
                           ("TEXTCOLOR", (0, 0), (0, -1), GREY), ("TEXTCOLOR", (2, 0), (2, -1), GREY),
                           ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#d8d0c0")),
                           ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    S += [Spacer(1, 4 * mm), t]

    src = project.get("analyse_source")
    S.append(Paragraph("Provenance de l'analyse", h2))
    if src == "simulated":
        S.append(Paragraph(_t("ANALYSE SIMULÉE : le contenu du plan n'a pas été lu. Les murs et les "
                              "quantités ci-dessous sont des valeurs de démonstration, à ne pas "
                              "utiliser pour une commande ou une fabrication."), warn))
    elif src:
        S.append(Paragraph(_t(f"Lecture réelle du plan (format {src.upper()})."), body))
    for note in project.get("analyse_notes") or []:
        S.append(Paragraph(_t("• " + note), small))

    S.append(Paragraph("Murs et ouvertures", h2))
    if walls:
        rows = [["Mur", "Long. (m)", "Haut. (m)", "Brut (m²)", "Ouvert. (m²)", "Net (m²)", "Angle"]]
        for w in walls:
            rows.append([_t(w["nom"]), _num(w["longueur_m"], 2), _num(w["hauteur_m"], 2),
                         _num(w["brut_m2"], 2), _num(w["ouvertures_m2"], 2), _num(w["net_m2"], 2),
                         "oui" if w["angle"] else "non"])
        rows.append(["Total", "", "", _num(sum(Decimal(str(w["brut_m2"])) for w in walls), 2),
                     _num(sum(Decimal(str(w["ouvertures_m2"])) for w in walls), 2),
                     _num(sum(Decimal(str(w["net_m2"])) for w in walls), 2), ""])
        S.append(_grid(rows, [52, 20, 20, 24, 26, 24, 14], total=True))
    else:
        S.append(Paragraph("Aucun mur : le plan n'a pas encore été analysé.", body))

    S.append(Paragraph("Nomenclature (blocs à fabriquer)", h2))
    if bom and bom["lignes"]:
        rows = [["Code", "Désignation", "Produit", "Quantité", "Poids tot. (kg)"]]
        for ln in bom["lignes"]:
            rows.append([_t(ln["code"]), _t(ln["nom"]), _t(ln["produit"]), _num(ln["quantite"]),
                         _num(ln["poids_kg"], 1) if ln.get("poids_kg") is not None else "-"])
        rows.append(["Total", "", "", _num(bom["total_blocs"]),
                     _num(bom["poids_total_kg"], 1) if bom.get("poids_total_kg") is not None else "-"])
        S.append(_grid(rows, [34, 58, 38, 24, 28], total=True, right_from=3))
        if bom.get("duree_estimee_min"):
            S.append(Paragraph(_t(f"Durée de fabrication INDICATIVE : {_num(bom['duree_estimee_min'])} min "
                                  "(cadences des moules, à confirmer sur la ligne)."), small))
        for a in bom.get("avertissements") or []:
            S.append(Paragraph(_t("Avertissement : " + a), warn))
    else:
        S.append(Paragraph("Aucun calepinage calculé pour ce projet.", body))

    if elevations:
        S.append(PageBreak())
        S.append(Paragraph("Calepinage assise par assise", h2))
        S.append(Paragraph(_t("Pose réelle bloc par bloc (joints décalés, ouvertures, linteaux, appuis, "
                              "chaînages, angles). Pièces claires = coupées. Les quantités à produire "
                              "ajoutent une marge de casse."), small))
        for el in elevations:
            d = el["detail"]
            head = Paragraph(_t(f"<b>{el['nom']}</b> - {d['longueur_mm']} x {d['hauteur_mm']} mm - "
                                f"{d['assises']} assises - {d['coupes']} coupe(s)"
                                + (f" - gamme {d['gamme']}" if d.get("gamme") else "")), body)
            notes = [Paragraph(_t("• " + n), small) for n in d.get("notes", [])[:3]]
            S.append(KeepTogether([Spacer(1, 3 * mm), head, Spacer(1, 1 * mm),
                                   WallElevation(d, el["formes"], doc.width, 70 * mm), *notes]))
        if elevations_omitted:
            S.append(Paragraph(_t(f"{elevations_omitted} autre(s) mur(s) : consultables dans l'application."),
                               small))

    if quote is not None:
        block: list = [Paragraph("Chiffrage estimatif (EUR et FCFA)", h2)]
        p = quote["parametres"]
        block.append(Paragraph(_t(
            f"Marge {_num(p['marge_pct'], 1)} % · TVA {_num(p['tva_pct'], 1)} % · "
            f"1 EUR = {_num(p['taux_fcfa_par_eur'], 3)} FCFA · "
            + ("devis FIGÉ à la validation" if quote.get("fige") else
               "devis INDICATIF au tarif du jour (non figé : le projet n'est pas validé)")), small))
        rows = [["Code", "Qté", "PU EUR", "Total EUR", "PU FCFA", "Total FCFA"]]
        for ln in quote["lignes"]:
            if ln["chiffre"]:
                rows.append([_t(ln["code"]), _num(ln["quantite"]), _num(ln["prix_unitaire_eur"], 2),
                             _num(ln["total_eur"], 2), _num(ln["prix_unitaire_fcfa"]),
                             _num(ln["total_fcfa"])])
            else:
                rows.append([_t(ln["code"]), _num(ln["quantite"]), "n/c", "n/c", "n/c", "n/c"])
        for label, key in (("Matériel HT", "materiel_ht"), ("Frais fixes", "frais_fixes"),
                           ("Total HT", "total_ht"), ("TVA", "tva"), ("Total TTC", "total_ttc")):
            rows.append([label, "", "", _num(quote["eur"][key], 2), "", _num(quote["fcfa"][key])])
        t = _grid(rows, [30, 20, 30, 34, 30, 36], right_from=1)
        n = len(rows)
        t.setStyle(TableStyle([("FONT", (0, n - 5), (-1, -1), "Helvetica-Bold", 9),
                               ("LINEABOVE", (0, n - 5), (-1, n - 5), 0.8, INK),
                               ("BACKGROUND", (0, n - 1), (-1, n - 1), colors.HexColor("#f3e6d0"))]))
        block.append(t)
        for a in quote.get("avertissements") or []:
            block.append(Paragraph(_t("Attention : " + a), warn))
        block.append(Paragraph(_t("Estimation non contractuelle : les coûts de revient par moule, la marge, la TVA "
                              "et le taux de change sont des valeurs paramétrables, à confirmer."), small))
        S.append(KeepTogether(block))

    S.append(Spacer(1, 10 * mm))
    S.append(Paragraph(_t("Signatures"), h2))
    sig = Table([["Chef de projet", "Client / maître d'ouvrage"], ["\n\n\n", "\n\n\n"]],
                colWidths=[88 * mm, 88 * mm])
    sig.setStyle(TableStyle([("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
                             ("BOX", (0, 1), (0, 1), 0.4, GREY), ("BOX", (1, 1), (1, 1), 0.4, GREY)]))
    S.append(sig)

    if mold_sheets:
        S.append(NextPageTemplate("sheet"))
        for i, (_, prims) in enumerate(mold_sheets):
            S += [PageBreak(), MoldSheet(prims)]
            if i < len(mold_sheets) - 1:
                S.append(NextPageTemplate("sheet"))
    doc.build(S)
    return buf.getvalue()


def _grid(rows: list[list[str]], widths_mm: list[float], total: bool = False,
          right_from: int = 1) -> Table:
    t = Table(rows, colWidths=[w * mm for w in widths_mm], repeatRows=1)
    style = [("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8.5), ("FONT", (0, 1), (-1, -1), "Helvetica", 8.5),
             ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#efe3c8")),
             ("ALIGN", (right_from, 0), (-1, -1), "RIGHT"),
             ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#faf6ec")]),
             ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#d8d0c0")),
             ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
    if total:
        style += [("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 8.5),
                  ("LINEABOVE", (0, -1), (-1, -1), 0.8, INK)]
    t.setStyle(TableStyle(style))
    return t
