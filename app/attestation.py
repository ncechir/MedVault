"""Génère l'attestation PDF d'une autorisation d'accès (cachet et signature).

Document généré systématiquement lorsque le délégué accepte une demande, et
re-téléchargeable ensuite depuis l'autorisation correspondante. Mise en page
inspirée d'un certificat : titre centré, formule « Je soussigné… certifie… »,
champs à compléter, mention de décision, cadres « cachet » et « signature ».
Aux couleurs du site (bleu et crevette). Entièrement dessiné en vecteur
(aucune image) : stable d'une exécution à l'autre, léger, lisible en noir et blanc.
"""
from __future__ import annotations

import io
import math
from datetime import datetime
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

LARGEUR, HAUTEUR = A4

# Logo du site (même fichiers que la page web)
DOSSIER_LOGOS = Path(__file__).resolve().parent.parent / "frontend" / "assets"
MARGE = 22 * mm

ENCRE = (0.106, 0.169, 0.267)      # #1B2B44
ARDOISE = (0.353, 0.416, 0.502)    # #5A6A80
BLEU = (0.184, 0.365, 0.549)       # #2F5D8C
CREVETTE = (0.851, 0.416, 0.325)   # #D96A53
TRAIT = (0.867, 0.894, 0.929)      # #DDE4ED
FOND = (0.929, 0.953, 0.980)       # #EDF3FA
BLANC = (1, 1, 1)


def _c(canv: canvas.Canvas, couleur: tuple[float, float, float]) -> None:
    canv.setFillColorRGB(*couleur)


def _trait(canv: canvas.Canvas, x1: float, y: float, x2: float,
           couleur=TRAIT, epaisseur: float = 0.6) -> None:
    canv.setStrokeColorRGB(*couleur)
    canv.setLineWidth(epaisseur)
    canv.line(x1, y, x2, y)


def _decouper(canv: canvas.Canvas, texte: str, police: str, taille: float,
              largeur_max: float) -> list[str]:
    lignes: list[str] = []
    courante = ""
    for mot in texte.split():
        essai = f"{courante} {mot}".strip()
        if canv.stringWidth(essai, police, taille) <= largeur_max:
            courante = essai
        else:
            if courante:
                lignes.append(courante)
            courante = mot
    if courante:
        lignes.append(courante)
    return lignes or ["—"]


def _texte_espace(canv: canvas.Canvas, x: float, y: float, texte: str, police: str,
                  taille: float, espace: float, centre: bool = False) -> None:
    """Texte avec espacement entre les lettres (comme le nom du site)."""
    largeur = sum(canv.stringWidth(c, police, taille) + espace for c in texte) - espace
    if centre:
        x -= largeur / 2
    canv.setFont(police, taille)
    for c in texte:
        canv.drawString(x, y, c)
        x += canv.stringWidth(c, police, taille) + espace


def _bouclier(canv: canvas.Canvas, x: float, y: float, h: float) -> None:
    """Petit bouclier bleu orné d'un cadenas, dessiné en vecteur."""
    l = h * 0.82
    canv.saveState()
    canv.translate(x, y)
    chemin = canv.beginPath()
    chemin.moveTo(l / 2, h)
    chemin.curveTo(l * 0.75, h * 0.97, l * 0.92, h * 0.93, l, h * 0.88)
    chemin.lineTo(l, h * 0.5)
    chemin.curveTo(l, h * 0.25, l * 0.7, h * 0.08, l / 2, 0)
    chemin.curveTo(l * 0.3, h * 0.08, 0, h * 0.25, 0, h * 0.5)
    chemin.lineTo(0, h * 0.88)
    chemin.curveTo(l * 0.08, h * 0.93, l * 0.25, h * 0.97, l / 2, h)
    chemin.close()
    canv.setFillColorRGB(*BLEU)
    canv.drawPath(chemin, stroke=0, fill=1)
    # cadenas blanc
    canv.setStrokeColorRGB(*BLANC)
    canv.setLineWidth(h * 0.055)
    cx, base = l / 2, h * 0.38
    canv.arc(cx - l * 0.17, base + h * 0.14, cx + l * 0.17, base + h * 0.44, 0, 180)
    canv.line(cx - l * 0.17, base + h * 0.29, cx - l * 0.17, base + h * 0.2)
    canv.line(cx + l * 0.17, base + h * 0.29, cx + l * 0.17, base + h * 0.2)
    canv.setFillColorRGB(*BLANC)
    canv.roundRect(cx - l * 0.25, base - h * 0.04, l * 0.5, h * 0.27, h * 0.03, stroke=0, fill=1)
    canv.setFillColorRGB(*BLEU)
    canv.circle(cx, base + h * 0.1, h * 0.03, stroke=0, fill=1)
    canv.restoreState()


def _ecg(canv: canvas.Canvas, x1: float, x2: float, y: float) -> None:
    """Ligne continue avec un battement de cœur au centre, comme l'en-tête du site."""
    centre = (x1 + x2) / 2
    k = 0.5  # taille du battement
    canv.setStrokeColorRGB(*BLEU)
    canv.setLineWidth(1.1)
    p = canv.beginPath()
    p.moveTo(x1, y)
    p.lineTo(centre - 14 * mm * k, y)
    p.lineTo(centre - 11 * mm * k, y + 3 * mm * k)
    p.lineTo(centre - 8 * mm * k, y)
    p.lineTo(centre - 5.5 * mm * k, y)
    p.lineTo(centre - 3.5 * mm * k, y - 3 * mm * k)
    p.lineTo(centre - 0.5 * mm * k, y + 10 * mm * k)
    p.lineTo(centre + 2.5 * mm * k, y - 9 * mm * k)
    p.lineTo(centre + 4.5 * mm * k, y)
    p.lineTo(centre + 8 * mm * k, y)
    p.lineTo(centre + 11 * mm * k, y + 4 * mm * k)
    p.lineTo(centre + 14 * mm * k, y)
    p.lineTo(x2, y)
    canv.drawPath(p, stroke=1, fill=0)


def _entete(canv: canvas.Canvas, reference: str, titre: str = "ATTESTATION D'ACCÈS",
            sous_titre: str = "AUX DONNÉES DE SANTÉ PSEUDONYMISÉES") -> float:
    y = HAUTEUR - 22 * mm
    bouclier = DOSSIER_LOGOS / "bouclier.png"
    mot = DOSSIER_LOGOS / "medvault-texte.png"
    if bouclier.exists() and mot.exists():
        # logo et nom du site (images)
        h_b = 17 * mm
        canv.drawImage(str(bouclier), MARGE, y - 11 * mm, width=h_b * 326 / 360, height=h_b,
                       mask="auto", preserveAspectRatio=True)
        x_t = MARGE + h_b * 326 / 360 + 4 * mm
        l_m = 40 * mm
        canv.drawImage(str(mot), x_t, y - 2.5 * mm, width=l_m, height=l_m * 62 / 563,
                       mask="auto", preserveAspectRatio=True)
        _c(canv, ARDOISE)
        _texte_espace(canv, x_t, y - 8.5 * mm, "VOTRE COFFRE-FORT DE DONNÉES MÉDICALES",
                      "Helvetica", 5.6, 1.0)
    else:  # images absentes : version dessinée
        _bouclier(canv, MARGE, y - 7 * mm, 14 * mm)
        _c(canv, BLEU)
        _texte_espace(canv, MARGE + 17 * mm, y - 1 * mm, "MEDVAULT", "Helvetica-Bold", 15, 3.2)
        _c(canv, ARDOISE)
        _texte_espace(canv, MARGE + 17 * mm, y - 6 * mm, "VOTRE COFFRE-FORT DE DONNÉES MÉDICALES",
                      "Helvetica", 5.6, 1.0)

    # référence, à droite
    _c(canv, ARDOISE)
    canv.setFont("Helvetica", 7.5)
    canv.drawRightString(LARGEUR - MARGE, y + 1 * mm, "RÉFÉRENCE")
    _c(canv, ENCRE)
    canv.setFont("Helvetica-Bold", 10)
    canv.drawRightString(LARGEUR - MARGE, y - 4.5 * mm, reference)

    y -= 22 * mm
    _c(canv, ENCRE)
    canv.setFont("Helvetica-Bold", 22)
    canv.drawCentredString(LARGEUR / 2, y, titre)
    y -= 7 * mm
    _c(canv, ARDOISE)
    canv.setFont("Helvetica", 10)
    canv.drawCentredString(LARGEUR / 2, y, sous_titre)
    y -= 9 * mm
    _ecg(canv, MARGE, LARGEUR - MARGE, y)
    return y - 14 * mm


def _ligne_champ(canv: canvas.Canvas, x: float, y: float, libelle: str, valeur: str,
                 largeur: float) -> float:
    """« Libellé  valeur » posé sur un filet, comme les champs d'un formulaire."""
    _c(canv, ARDOISE)
    canv.setFont("Helvetica", 9.5)
    canv.drawString(x, y, libelle)
    decalage = canv.stringWidth(libelle, "Helvetica", 9.5) + 4 * mm
    _c(canv, ENCRE)
    lignes = _decouper(canv, valeur or "—", "Helvetica-Bold", 10.5, largeur - decalage)
    for i, ligne in enumerate(lignes):
        canv.setFont("Helvetica-Bold", 10.5)
        canv.drawString(x + decalage, y, ligne)
        _trait(canv, x + decalage - 1.5 * mm, y - 1.8 * mm, x + largeur)
        y -= 6 * mm
    return y - 2.5 * mm


def _bloc(canv: canvas.Canvas, x: float, y: float, libelle: str, valeur: str,
          largeur: float) -> float:
    """Libellé en petites capitales bleues, valeur dessous (champs longs)."""
    _c(canv, BLEU)
    canv.setFont("Helvetica-Bold", 8)
    canv.drawString(x, y, libelle.upper())
    y -= 5 * mm
    _c(canv, ENCRE)
    canv.setFont("Helvetica", 10)
    for ligne in _decouper(canv, valeur or "—", "Helvetica", 10, largeur):
        canv.drawString(x, y, ligne)
        y -= 4.8 * mm
    return y - 3 * mm


def _cadre(canv: canvas.Canvas, x: float, y: float, l: float, h: float) -> None:
    canv.setStrokeColorRGB(*BLEU)
    canv.setLineWidth(0.9)
    canv.roundRect(x, y, l, h, 2 * mm, stroke=1, fill=0)


def _cachet(canv: canvas.Canvas, cx: float, cy: float, date_texte: str) -> None:
    rayon_ext, rayon_int = 16.5 * mm, 12.6 * mm
    canv.saveState()
    canv.setStrokeColorRGB(*CREVETTE)
    canv.setLineWidth(1.4)
    canv.circle(cx, cy, rayon_ext, stroke=1, fill=0)
    canv.setLineWidth(0.7)
    canv.circle(cx, cy, rayon_int, stroke=1, fill=0)

    texte_haut = "DÉLÉGUÉ À LA PROTECTION DES DONNÉES · CHU SOPHIA · "
    _c(canv, CREVETTE)
    canv.setFont("Helvetica-Bold", 6)
    rayon_texte = (rayon_ext + rayon_int) / 2
    angle_depart = 90
    total = canv.stringWidth(texte_haut, "Helvetica-Bold", 6)
    etirement = (2 * math.pi * rayon_texte) / total  # le texte fait exactement le tour du cachet
    for caractere in texte_haut:
        largeur = canv.stringWidth(caractere, "Helvetica-Bold", 6)
        angle_pas = (largeur * etirement / rayon_texte) * (180 / math.pi)
        canv.saveState()
        canv.translate(cx + rayon_texte * math.cos(math.radians(angle_depart)),
                       cy + rayon_texte * math.sin(math.radians(angle_depart)))
        canv.rotate(angle_depart - 90)
        canv.drawCentredString(0, 0, caractere)
        canv.restoreState()
        angle_depart -= angle_pas

    canv.setFont("Helvetica-Bold", 8)
    canv.drawCentredString(cx, cy + 1.5 * mm, "ACCÈS")
    canv.drawCentredString(cx, cy - 2.5 * mm, "AUTORISÉ")
    canv.setFont("Helvetica", 5.8)
    canv.drawCentredString(cx, cy - 6 * mm, date_texte)
    canv.restoreState()


def _signature(canv: canvas.Canvas, x: float, y: float) -> None:
    canv.saveState()
    canv.setStrokeColorRGB(*BLEU)
    canv.setLineWidth(1.1)
    p = canv.beginPath()
    p.moveTo(x, y)
    p.curveTo(x + 6 * mm, y + 9 * mm, x + 12 * mm, y - 7 * mm, x + 20 * mm, y + 4 * mm)
    p.curveTo(x + 26 * mm, y + 11 * mm, x + 30 * mm, y - 4 * mm, x + 38 * mm, y + 2 * mm)
    p.curveTo(x + 43 * mm, y + 6 * mm, x + 46 * mm, y - 2 * mm, x + 50 * mm, y + 1 * mm)
    canv.drawPath(p, stroke=1, fill=0)
    canv.restoreState()


def generer(*, reference: str, titre_projet: str, finalite: str, demandeur_nom: str,
            demandeur_service: str, dpo_nom: str, motif: str, conditions: str,
            date_debut: datetime, date_fin: datetime, date_purge: datetime,
            colonnes: list[str], services: list[str], prise_le: datetime) -> bytes:
    tampon = io.BytesIO()
    canv = canvas.Canvas(tampon, pagesize=A4)
    largeur_utile = LARGEUR - 2 * MARGE

    y = _entete(canv, reference)

    # --- formule du certificat ---
    _c(canv, ENCRE)
    canv.setFont("Helvetica", 11)
    canv.drawString(MARGE, y, "Je soussigné(e),")
    y = _ligne_champ(canv, MARGE + 30 * mm, y, "", dpo_nom, largeur_utile - 30 * mm)
    canv.setFont("Helvetica", 10)
    _c(canv, ARDOISE)
    canv.drawString(MARGE, y + 1 * mm, "Délégué à la protection des données du CHU Sophia,")
    y -= 7 * mm
    _c(canv, ENCRE)
    canv.setFont("Helvetica", 11)
    canv.drawString(MARGE, y, "certifie avoir examiné ce jour la demande d'accès déposée par :")
    y -= 11 * mm

    retrait = 12 * mm
    larg = largeur_utile - retrait
    y = _ligne_champ(canv, MARGE + retrait, y, "Nom et prénom", demandeur_nom, larg)
    y = _ligne_champ(canv, MARGE + retrait, y, "Service", demandeur_service, larg)
    y = _ligne_champ(canv, MARGE + retrait, y, "Projet", titre_projet, larg)
    y -= 3 * mm

    # --- détails de l'autorisation, dans un encart ---
    detail = [("Finalité déclarée", finalite)]
    if services:
        detail.append(("Services concernés", ", ".join(services)))
    if colonnes:
        detail.append(("Données autorisées", ", ".join(colonnes)))
    if conditions:
        detail.append(("Conditions particulières", conditions))

    # hauteur de l'encart : on mesure d'abord
    hauteur = 6 * mm
    for libelle, valeur in detail:
        hauteur += 5 * mm + 4.8 * mm * len(_decouper(canv, valeur or "—", "Helvetica", 10,
                                                      largeur_utile - 10 * mm)) + 3 * mm
    haut = y + 2 * mm
    _c(canv, FOND)
    canv.setStrokeColorRGB(*TRAIT)
    canv.roundRect(MARGE, haut - hauteur, largeur_utile, hauteur, 2 * mm, stroke=1, fill=1)
    _c(canv, CREVETTE)
    canv.rect(MARGE, haut - hauteur, 1.6 * mm, hauteur, stroke=0, fill=1)
    yy = haut - 7 * mm
    for libelle, valeur in detail:
        yy = _bloc(canv, MARGE + 6 * mm, yy, libelle, valeur, largeur_utile - 12 * mm)
    y = haut - hauteur - 8 * mm

    # --- décision ---
    _c(canv, ENCRE)
    canv.setFont("Helvetica-Bold", 10.5)
    canv.drawString(MARGE, y, "La demande est acceptée. L'accès aux données pseudonymisées est ouvert")
    y -= 5.5 * mm
    canv.drawString(MARGE, y, f"du {date_debut.strftime('%d/%m/%Y')} au {date_fin.strftime('%d/%m/%Y')}"
                              f", puis les données sont purgées le {date_purge.strftime('%d/%m/%Y')}.")
    y -= 8 * mm
    _c(canv, ARDOISE)
    canv.setFont("Helvetica", 9)
    canv.drawString(MARGE, y, "Aucune identité de patient n'est transmise. Chaque accès est journalisé "
                              "et se referme seul à son terme.")

    # --- date, cachet, signature ---
    y -= 10 * mm
    _c(canv, ENCRE)
    canv.setFont("Helvetica", 10.5)
    canv.drawRightString(LARGEUR - MARGE - 46 * mm, y, "Date")
    canv.setFont("Helvetica-Bold", 10.5)
    canv.drawString(LARGEUR - MARGE - 42 * mm, y, prise_le.strftime("%d/%m/%Y"))
    _trait(canv, LARGEUR - MARGE - 44 * mm, y - 1.8 * mm, LARGEUR - MARGE)

    y -= 12 * mm
    _c(canv, BLEU)
    canv.setFont("Helvetica-Bold", 9)
    canv.drawString(MARGE + 4 * mm, y, "Cachet du délégué")
    canv.drawString(LARGEUR / 2 + 8 * mm, y, "Signature du délégué")

    cadre_h = 38 * mm
    cadre_l = (largeur_utile - 12 * mm) / 2
    bas = y - 4 * mm - cadre_h
    _cadre(canv, MARGE, bas, cadre_l, cadre_h)
    _cadre(canv, LARGEUR - MARGE - cadre_l, bas, cadre_l, cadre_h)
    _cachet(canv, MARGE + cadre_l / 2, bas + cadre_h / 2, f"Le {prise_le.strftime('%d/%m/%Y')}")
    sx = LARGEUR - MARGE - cadre_l + 8 * mm
    _signature(canv, sx, bas + cadre_h / 2 + 3 * mm)
    _c(canv, ARDOISE)
    canv.setFont("Helvetica", 8)
    canv.drawString(sx, bas + 9 * mm, dpo_nom)

    # --- pied de page ---
    _trait(canv, MARGE, 20 * mm, LARGEUR - MARGE)
    _c(canv, ARDOISE)
    canv.setFont("Helvetica", 7.5)
    canv.drawString(MARGE, 15 * mm,
                    "Document généré automatiquement par le portail MedVault — "
                    "ne constitue pas une pièce d'identité.")
    canv.drawString(MARGE, 11 * mm, "Toute falsification est passible de poursuites.")
    canv.drawRightString(LARGEUR - MARGE, 15 * mm, f"Réf. {reference}")

    canv.showPage()
    canv.save()
    return tampon.getvalue()
