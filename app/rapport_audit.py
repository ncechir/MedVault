"""Rapport d'audit PDF : preuve d'intégrité du journal et synthèse d'activité."""
import io
from collections import Counter
from datetime import date, datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from app.attestation import (
    ARDOISE, BLANC, BLEU, CREVETTE, ENCRE, FOND, HAUTEUR, LARGEUR, MARGE, TRAIT,
    _c, _decouper, _entete, _trait,
)

VERT = (0.18, 0.49, 0.36)   # #2E7D5B
ROUGE = (0.70, 0.15, 0.12)  # #B3261E

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
    """Même mise en page que l'attestation d'accès : en-tête, encarts, pied de page."""
    tampon = io.BytesIO()
    canv = canvas.Canvas(tampon, pagesize=A4)
    canv.setTitle("Rapport d'audit MedVault")
    canv.setAuthor("MedVault")
    largeur_utile = LARGEUR - 2 * MARGE
    reference = f"AUD-{genere_le:%Y%m%d-%H%M}"

    if debut or fin:
        periode = ((f"du {debut:%d/%m/%Y}" if debut else "depuis l'origine")
                   + (f" au {fin:%d/%m/%Y}" if fin else " à ce jour"))
    else:
        periode = "ensemble du journal"

    def pied() -> None:
        _trait(canv, MARGE, 20 * mm, LARGEUR - MARGE)
        _c(canv, ARDOISE)
        canv.setFont("Helvetica", 7.5)
        canv.drawString(MARGE, 15 * mm, "Document généré automatiquement par le portail MedVault — "
                                        "ne constitue pas une certification de conformité.")
        canv.drawString(MARGE, 11 * mm, "Données synthétiques · CHU Sophia.")
        canv.drawRightString(LARGEUR - MARGE, 15 * mm, f"Réf. {reference}")

    etat = {"y": _entete(canv, reference, "RAPPORT D'AUDIT",
                         "INTÉGRITÉ DU JOURNAL ET ACTIVITÉ")}

    def place(hauteur: float) -> None:
        """Passe à une nouvelle page si le bloc ne tient pas."""
        if etat["y"] - hauteur < 28 * mm:
            pied()
            canv.showPage()
            etat["y"] = HAUTEUR - 25 * mm

    def titre_section(texte: str) -> None:
        place(34 * mm)
        _c(canv, BLEU)
        canv.setFont("Helvetica-Bold", 8.5)
        canv.drawString(MARGE, etat["y"], texte.upper())
        etat["y"] -= 3 * mm

    def encart(lignes: list[tuple[str, str, tuple]], taille: float = 10) -> None:
        """Encart bleu clair avec liseré crevette ; lignes = (texte, police, couleur)."""
        interne = largeur_utile - 12 * mm
        rendu = []
        for texte, police, couleur in lignes:
            for morceau in _decouper(canv, texte, police, taille, interne):
                rendu.append((morceau, police, couleur))
        hauteur = len(rendu) * 4.8 * mm + 8 * mm
        place(hauteur + 6 * mm)
        haut = etat["y"]
        _c(canv, FOND)
        canv.setStrokeColorRGB(*TRAIT)
        canv.roundRect(MARGE, haut - hauteur, largeur_utile, hauteur, 2 * mm, stroke=1, fill=1)
        _c(canv, CREVETTE)
        canv.rect(MARGE, haut - hauteur, 1.6 * mm, hauteur, stroke=0, fill=1)
        yy = haut - 6.5 * mm
        for texte, police, couleur in rendu:
            _c(canv, couleur)
            canv.setFont(police, taille)
            canv.drawString(MARGE + 6 * mm, yy, texte)
            yy -= 4.8 * mm
        etat["y"] = haut - hauteur - 6 * mm

    # --- en-tête du document ---
    y = etat["y"]
    _c(canv, ENCRE)
    canv.setFont("Helvetica", 10.5)
    canv.drawString(MARGE, y, "Période")
    canv.setFont("Helvetica-Bold", 10.5)
    canv.drawString(MARGE + 24 * mm, y, periode)
    _trait(canv, MARGE + 22 * mm, y - 1.8 * mm, LARGEUR - MARGE)
    y -= 8 * mm
    _c(canv, ENCRE)
    canv.setFont("Helvetica", 10.5)
    canv.drawString(MARGE, y, "Généré le")
    canv.setFont("Helvetica-Bold", 10.5)
    canv.drawString(MARGE + 24 * mm, y,
                    f"{genere_le:%d/%m/%Y à %H:%M} par {par}")
    _trait(canv, MARGE + 22 * mm, y - 1.8 * mm, LARGEUR - MARGE)
    etat["y"] = y - 11 * mm

    # --- 1. intégrité ---
    titre_section("1. Intégrité du journal")
    etat["y"] -= 5 * mm
    if integrite["valide"]:
        statut = ("Chaîne intègre : aucune rupture détectée.", VERT)
    else:
        a = integrite["premiere_anomalie"]
        statut = (f"Anomalie détectée dès l'entrée n° {a['id']} : {a['motif']}. "
                  f"({integrite['nb_anomalies']} anomalie(s).)", ROUGE)
    encart([
        (statut[0], "Helvetica-Bold", statut[1]),
        (f"{integrite['nb_total']} entrée(s) au total, dont {integrite['nb_chainees']} "
         f"chaînée(s) par empreinte SHA-256 et {integrite['nb_anterieures']} antérieure(s) "
         f"à l'introduction du chaînage (non vérifiables).", "Helvetica", ENCRE),
    ])
    place(30 * mm)
    _c(canv, BLEU)
    canv.setFont("Helvetica-Bold", 8)
    canv.drawString(MARGE, etat["y"] + 2 * mm, "EMPREINTE DE TÊTE (À CONSERVER HORS DE LA BASE)")
    etat["y"] -= 4 * mm
    _c(canv, ENCRE)
    empreinte = integrite["empreinte_tete"] or "—"
    for i in range(0, len(empreinte), 64):
        canv.setFont("Courier", 8.5)
        canv.drawString(MARGE, etat["y"], empreinte[i:i + 64])
        etat["y"] -= 4.5 * mm
    etat["y"] -= 1 * mm
    _c(canv, ARDOISE)
    canv.setFont("Helvetica", 8)
    for ligne in _decouper(canv, integrite["avertissement"], "Helvetica", 8, largeur_utile):
        canv.drawString(MARGE, etat["y"], ligne)
        etat["y"] -= 4 * mm
    etat["y"] -= 5 * mm

    # --- 2. activité ---
    titre_section("2. Activité sur la période")
    etat["y"] -= 6 * mm
    compte = Counter(e.action for e in entrees)
    lignes = [(lib, compte[code]) for code, lib in LIBELLES.items() if compte.get(code)]
    if not lignes:
        lignes = [("Aucun événement de ce type sur la période", 0)]
    place(14 * mm)
    canv.setStrokeColorRGB(*TRAIT)
    _c(canv, BLEU)
    canv.setFont("Helvetica-Bold", 8)
    canv.drawString(MARGE, etat["y"], "ÉVÉNEMENT")
    canv.drawRightString(LARGEUR - MARGE, etat["y"], "NOMBRE")
    _trait(canv, MARGE, etat["y"] - 2 * mm, LARGEUR - MARGE, BLEU, 0.9)
    etat["y"] -= 7 * mm
    for libelle, n in lignes:
        place(10 * mm)
        _c(canv, ENCRE)
        canv.setFont("Helvetica", 10)
        canv.drawString(MARGE, etat["y"], libelle)
        canv.setFont("Helvetica-Bold", 10)
        canv.drawRightString(LARGEUR - MARGE, etat["y"], str(n))
        _trait(canv, MARGE, etat["y"] - 2 * mm, LARGEUR - MARGE)
        etat["y"] -= 6 * mm
    etat["y"] -= 4 * mm

    # --- 3. politique ---
    titre_section("3. Politique de confidentialité en vigueur")
    etat["y"] -= 5 * mm
    actions = {"AVERTIR": "avertir", "SUPPRIMER": "retirer les petits groupes",
               "BLOQUER": "bloquer l'export"}
    encart([
        (politique.nom, "Helvetica-Bold", ENCRE),
        (f"Seuil de k-anonymat k ≥ {politique.k_min}, "
         f"action : {actions.get(politique.action, politique.action)}"
         + (f", export limité à {politique.max_lignes_export} lignes."
            if politique.max_lignes_export else "."), "Helvetica", ENCRE),
    ])

    # --- 4. portée ---
    titre_section("4. Portée et limites")
    etat["y"] -= 5 * mm
    encart([
        ("Ce rapport décrit l'activité enregistrée par le portail ; il ne constitue pas "
         "une certification de conformité. Le contrôle k-anonymat porte sur les colonnes "
         "livrées et ne tient pas compte des données détenues par des tiers.",
         "Helvetica", ENCRE),
    ], taille=9.5)

    pied()
    canv.showPage()
    canv.save()
    return tampon.getvalue()
