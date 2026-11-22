"""Génère l'attestation PDF d'une autorisation d'accès (tampon et signature).

Document généré systématiquement lorsque le délégué accepte une demande, et
re-téléchargeable ensuite depuis l'autorisation correspondante. Entièrement
dessiné en vecteur (aucune image) : stable d'une exécution à l'autre, léger,
et lisible même imprimé en noir et blanc.
"""
from __future__ import annotations

import io
import math
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

LARGEUR, HAUTEUR = A4

ENCRE = (0.11, 0.14, 0.20)
ARDOISE = (0.33, 0.38, 0.45)
INDIGO = (0.23, 0.28, 0.63)
VERT = (0.09, 0.45, 0.27)
TRAIT = (0.82, 0.84, 0.88)
BLANC = (1, 1, 1)


def _c(canv: canvas.Canvas, couleur: tuple[float, float, float]) -> None:
    canv.setFillColorRGB(*couleur)


def _ligne_trait(canv: canvas.Canvas, x: float, y: float, largeur: float) -> None:
    canv.setStrokeColorRGB(*TRAIT)
    canv.setLineWidth(0.6)
    canv.line(x, y, x + largeur, y)


def _entete(canv: canvas.Canvas, reference: str) -> float:
    y = HAUTEUR - 25 * mm
    _c(canv, ENCRE)
    canv.setFont("Helvetica-Bold", 18)
    canv.drawString(20 * mm, y, "Attestation d'autorisation d'accès")
    y -= 7 * mm
    _c(canv, ARDOISE)
    canv.setFont("Helvetica", 10)
    canv.drawString(20 * mm, y, "Portail d'accès aux données de santé pseudonymisées")
    y -= 10 * mm
    _c(canv, INDIGO)
    canv.setFont("Helvetica-Bold", 11)
    canv.drawString(20 * mm, y, f"Référence : {reference}")
    y -= 6 * mm
    _ligne_trait(canv, 20 * mm, y, LARGEUR - 40 * mm)
    return y - 8 * mm


def _champ(canv: canvas.Canvas, x: float, y: float, libelle: str, valeur: str,
           largeur: float = 170) -> float:
    _c(canv, ARDOISE)
    canv.setFont("Helvetica", 9)
    canv.drawString(x, y, libelle.upper())
    y -= 5 * mm
    _c(canv, ENCRE)
    canv.setFont("Helvetica", 11)
    for ligne in _decouper(canv, valeur or "—", "Helvetica", 11, largeur * mm):
        canv.drawString(x, y, ligne)
        y -= 5.2 * mm
    return y - 2 * mm


def _decouper(canv: canvas.Canvas, texte: str, police: str, taille: int,
              largeur_max: float) -> list[str]:
    mots = texte.split()
    lignes: list[str] = []
    courante = ""
    for mot in mots:
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


def _tampon(canv: canvas.Canvas, cx: float, cy: float, date_texte: str) -> None:
    rayon_ext, rayon_int = 20 * mm, 15.5 * mm
    canv.saveState()
    canv.setStrokeColorRGB(*VERT)
    canv.setLineWidth(1.4)
    canv.circle(cx, cy, rayon_ext, stroke=1, fill=0)
    canv.setLineWidth(0.7)
    canv.circle(cx, cy, rayon_int, stroke=1, fill=0)

    texte_haut = "DEMANDE AUTORISÉE · DÉLÉGUÉ À LA PROTECTION DES DONNÉES ·"
    _c(canv, VERT)
    canv.setFont("Helvetica-Bold", 6.3)
    rayon_texte = (rayon_ext + rayon_int) / 2
    angle_depart = 90
    for caractere in texte_haut:
        largeur = canv.stringWidth(caractere, "Helvetica-Bold", 6.3)
        angle_pas = (largeur / rayon_texte) * (180 / math.pi)
        angle = angle_depart
        canv.saveState()
        canv.translate(cx + rayon_texte * math.cos(math.radians(angle)),
                        cy + rayon_texte * math.sin(math.radians(angle)))
        canv.rotate(angle - 90)
        canv.drawCentredString(0, 0, caractere)
        canv.restoreState()
        angle_depart -= angle_pas

    canv.setFont("Helvetica-Bold", 9.5)
    canv.drawCentredString(cx, cy + 2 * mm, "ACCÈS")
    canv.drawCentredString(cx, cy - 3 * mm, "AUTORISÉ")
    canv.setFont("Helvetica", 6.5)
    canv.drawCentredString(cx, cy - 7.5 * mm, date_texte)
    canv.restoreState()


def _signature(canv: canvas.Canvas, x: float, y: float, nom: str) -> None:
    canv.saveState()
    canv.setStrokeColorRGB(*INDIGO)
    canv.setLineWidth(1.1)
    chemin = canv.beginPath()
    chemin.moveTo(x, y)
    chemin.curveTo(x + 6 * mm, y + 9 * mm, x + 12 * mm, y - 7 * mm, x + 20 * mm, y + 4 * mm)
    chemin.curveTo(x + 26 * mm, y + 11 * mm, x + 30 * mm, y - 4 * mm, x + 38 * mm, y + 2 * mm)
    chemin.curveTo(x + 43 * mm, y + 6 * mm, x + 46 * mm, y - 2 * mm, x + 50 * mm, y + 1 * mm)
    canv.drawPath(chemin, stroke=1, fill=0)
    canv.restoreState()
    _ligne_trait(canv, x, y - 4 * mm, 55 * mm)
    _c(canv, ARDOISE)
    canv.setFont("Helvetica", 8)
    canv.drawString(x, y - 9 * mm, nom)
    canv.drawString(x, y - 13 * mm, "Délégué à la protection des données")


def generer(*, reference: str, titre_projet: str, finalite: str, demandeur_nom: str,
            demandeur_service: str, dpo_nom: str, motif: str, conditions: str,
            date_debut: datetime, date_fin: datetime, date_purge: datetime,
            colonnes: list[str], services: list[str], prise_le: datetime) -> bytes:
    tampon = io.BytesIO()
    canv = canvas.Canvas(tampon, pagesize=A4)

    y = _entete(canv, reference)
    marge = 20 * mm
    y = _champ(canv, marge, y, "Chercheur", f"{demandeur_nom} — {demandeur_service}")
    y = _champ(canv, marge, y, "Intitulé du projet", titre_projet)
    y = _champ(canv, marge, y, "Finalité déclarée", finalite)
    if services:
        y = _champ(canv, marge, y, "Services concernés", ", ".join(services))
    if colonnes:
        y = _champ(canv, marge, y, "Données autorisées", ", ".join(colonnes), largeur=170)
    if conditions:
        y = _champ(canv, marge, y, "Conditions particulières", conditions)

    y -= 2 * mm
    _ligne_trait(canv, marge, y, LARGEUR - 2 * marge)
    y -= 8 * mm

    colonne_gauche, colonne_droite = marge, LARGEUR / 2 + 5 * mm
    _champ(canv, colonne_gauche, y, "Date de décision", prise_le.strftime("%d/%m/%Y"), largeur=70)
    _champ(canv, colonne_droite, y, "Accès ouvert jusqu'au", date_fin.strftime("%d/%m/%Y"), largeur=70)
    y -= 20 * mm
    _champ(canv, colonne_gauche, y, "Purge des données prévue le",
           date_purge.strftime("%d/%m/%Y"), largeur=70)

    _tampon(canv, LARGEUR - 42 * mm, 58 * mm, f"Le {prise_le.strftime('%d/%m/%Y')}")
    _signature(canv, marge, 50 * mm, dpo_nom)

    _c(canv, ARDOISE)
    canv.setFont("Helvetica", 7.5)
    canv.drawString(marge, 15 * mm,
                     "Document généré automatiquement par le portail — ne constitue pas une "
                     "pièce d'identité. Toute falsification est passible de poursuites.")

    canv.showPage()
    canv.save()
    return tampon.getvalue()
