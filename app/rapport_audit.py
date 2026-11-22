"""Rapport d'audit PDF : preuve d'intégrité du journal et synthèse d'activité."""
import io
from collections import Counter
from datetime import date, datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

BLEU = colors.HexColor("#2F5D8C")
CORAIL = colors.HexColor("#D96A53")
GRIS = colors.HexColor("#5B6770")

LIBELLES = {
    "DEMANDE_VALIDEE": "Accès accordés", "DEMANDE_REFUSEE": "Demandes refusées",
    "ACCES_REVOQUE": "Accès révoqués", "EXTRACTION_CONSULTEE": "Données consultées",
    "EXTRACTION_EXPORTEE": "Données exportées",
    "EXTRACTION_CONSULTEE_DPO": "Consultations en supervision",
    "EXTRACTION_EXPORTEE_DPO": "Exports en supervision",
    "EXPORT_BLOQUE_POLITIQUE": "Exports bloqués par une politique",
    "EXTRACTION_REFUSEE": "Extractions refusées",
    "DONNEES_IMPORTEES": "Jeux de données importés", "DONNEES_PURGEES": "Suppressions attestées",
    "POLITIQUE_MODIFIEE": "Politiques modifiées", "POLITIQUE_CREEE": "Politiques créées",
    "CONNEXION_ECHOUEE": "Échecs de connexion",
}


def generer(*, integrite: dict, entrees: list, politique, debut: date | None,
            fin: date | None, par: str, genere_le: datetime) -> bytes:
    tampon = io.BytesIO()
    doc = SimpleDocTemplate(tampon, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
                            topMargin=18 * mm, bottomMargin=18 * mm,
                            title="Rapport d'audit MedVault", author="MedVault")
    st = getSampleStyleSheet()
    titre = ParagraphStyle("t", parent=st["Title"], textColor=BLEU, fontSize=20,
                           alignment=0, spaceAfter=2)
    h2 = ParagraphStyle("h2", parent=st["Heading2"], textColor=BLEU, fontSize=12.5,
                        spaceBefore=12, spaceAfter=4)
    txt = ParagraphStyle("x", parent=st["BodyText"], fontSize=9.5, leading=13)
    petit = ParagraphStyle("p", parent=txt, fontSize=8, textColor=GRIS, leading=11)
    mono = ParagraphStyle("m", parent=txt, fontName="Courier", fontSize=8, leading=10)

    if debut or fin:
        periode = ("période : " + (f"du {debut:%d/%m/%Y}" if debut else "depuis l'origine")
                   + (f" au {fin:%d/%m/%Y}" if fin else " à ce jour"))
    else:
        periode = "période : ensemble du journal"

    el = [Paragraph("Rapport d'audit", titre),
          Paragraph(f"MedVault · CHU Sophia (données synthétiques) · {periode}", petit),
          Paragraph(f"Généré le {genere_le.strftime('%d/%m/%Y à %H:%M')} par {par}", petit)]

    el.append(Paragraph("1. Intégrité du journal", h2))
    if integrite["valide"]:
        etat = "<font color='#2E7D5B'><b>Chaîne intègre</b></font> : aucune rupture détectée."
    else:
        a = integrite["premiere_anomalie"]
        etat = (f"<font color='#B3261E'><b>Anomalie détectée</b></font> dès l'entrée "
                f"n° {a['id']} : {a['motif']}. ({integrite['nb_anomalies']} anomalie(s).)")
    el.append(Paragraph(etat, txt))
    el.append(Paragraph(
        f"{integrite['nb_total']} entrée(s) au total, dont {integrite['nb_chainees']} "
        f"chaînée(s) par empreinte SHA-256 et {integrite['nb_anterieures']} antérieure(s) "
        f"à l'introduction du chaînage (non vérifiables).", txt))
    el.append(Spacer(1, 4))
    el.append(Paragraph("Empreinte de tête (à conserver hors de la base) :", petit))
    el.append(Paragraph(integrite["empreinte_tete"] or "—", mono))
    el.append(Paragraph(integrite["avertissement"], petit))

    el.append(Paragraph("2. Activité sur la période", h2))
    compte = Counter(e.action for e in entrees)
    lignes = [["Événement", "Nombre"]]
    for code, lib in LIBELLES.items():
        if compte.get(code):
            lignes.append([lib, str(compte[code])])
    if len(lignes) == 1:
        lignes.append(["Aucun événement de ce type sur la période", "0"])
    tab = Table(lignes, colWidths=[120 * mm, 30 * mm])
    tab.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BLEU), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 9), ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F3F6F9")]),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#D5DDE5")),
    ]))
    el.append(tab)

    el.append(Paragraph("3. Politique de confidentialité en vigueur", h2))
    actions = {"AVERTIR": "avertir", "SUPPRIMER": "retirer les petits groupes",
               "BLOQUER": "bloquer l'export"}
    el.append(Paragraph(
        f"<b>{politique.nom}</b> : seuil de k-anonymat k ≥ {politique.k_min}, "
        f"action : {actions.get(politique.action, politique.action)}"
        + (f", export limité à {politique.max_lignes_export} lignes."
           if politique.max_lignes_export else "."), txt))

    el.append(Paragraph("4. Portée et limites", h2))
    el.append(Paragraph(
        "Ce rapport décrit l'activité enregistrée par le portail ; il ne constitue pas "
        "une certification de conformité. Le contrôle k-anonymat porte sur les colonnes "
        "livrées et ne tient pas compte des données détenues par des tiers.", txt))
    doc.build(el)
    return tampon.getvalue()
