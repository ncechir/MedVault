"""Construit le classeur Excel (.xlsx) d'une extraction, lisible et prêt à
l'analyse : colonnes groupées par thème, en-têtes mis en forme, tableau
structuré, et un second onglet pour les chiffres déjà agrégés.
"""
from __future__ import annotations

import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

ENCRE = "1C2433"
INDIGO = "3A478B"
SABLE = "F4F1EA"
TRAIT = "D1D4DE"
BLANC = "FFFFFF"


def construire(resultat: dict) -> bytes:
    """`resultat` a la forme renvoyée par `extraction.produire(...)` :
    {"colonnes": [{"code", "libelle", "groupe"}...], "lignes": [...], "statistiques": {...}}
    """
    classeur = Workbook()
    feuille = classeur.active
    feuille.title = "Extraction"

    colonnes = resultat["colonnes"]
    lignes = resultat["lignes"]

    # -- bande de groupes (ligne 1, fusionnée par groupe contigu) --
    groupe_fill = PatternFill("solid", fgColor=INDIGO)
    groupe_font = Font(color=BLANC, bold=True, size=10)
    i = 0
    while i < len(colonnes):
        groupe = colonnes[i].get("groupe") or "Données"
        debut = i
        while i < len(colonnes) and (colonnes[i].get("groupe") or "Données") == groupe:
            i += 1
        fin = i
        cellule = feuille.cell(row=1, column=debut + 1, value=groupe)
        cellule.fill = groupe_fill
        cellule.font = groupe_font
        cellule.alignment = Alignment(horizontal="center")
        if fin - debut > 1:
            feuille.merge_cells(start_row=1, start_column=debut + 1,
                                end_row=1, end_column=fin)
        for col in range(debut + 1, fin + 1):
            if col != debut + 1:
                feuille.cell(row=1, column=col).fill = groupe_fill

    # -- en-têtes (ligne 2) --
    entete_fill = PatternFill("solid", fgColor=ENCRE)
    entete_font = Font(color=BLANC, bold=True, size=10)
    for idx, colonne in enumerate(colonnes, start=1):
        cellule = feuille.cell(row=2, column=idx, value=colonne["libelle"])
        cellule.fill = entete_fill
        cellule.font = entete_font
        cellule.alignment = Alignment(horizontal="left", vertical="center")

    # -- données --
    for r, ligne in enumerate(lignes, start=3):
        for c, colonne in enumerate(colonnes, start=1):
            valeur = ligne.get(colonne["code"])
            cellule = feuille.cell(row=r, column=c, value=valeur)
            if r % 2 == 1:
                cellule.fill = PatternFill("solid", fgColor=SABLE)

    derniere_ligne = max(len(lignes) + 2, 3)
    if lignes:
        derniere_colonne_lettre = get_column_letter(len(colonnes))
        tableau = Table(ref=f"A2:{derniere_colonne_lettre}{derniere_ligne}",
                        displayName="Extraction")
        tableau.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=False)
        feuille.add_table(tableau)

    for idx, colonne in enumerate(colonnes, start=1):
        largeur = min(42, max(12, len(colonne["libelle"]) + 2))
        feuille.column_dimensions[get_column_letter(idx)].width = largeur

    feuille.freeze_panes = "A3"
    feuille.row_dimensions[1].height = 20
    feuille.row_dimensions[2].height = 20

    statistiques = resultat.get("statistiques") or []
    if statistiques:
        feuille_stats = classeur.create_sheet("Chiffres agrégés")
        for idx, titre in enumerate(("Colonne", "Valeur", "Effectif"), start=1):
            cellule = feuille_stats.cell(row=1, column=idx, value=titre)
            cellule.fill = PatternFill("solid", fgColor=ENCRE)
            cellule.font = Font(color=BLANC, bold=True)
        for r, ligne in enumerate(statistiques, start=2):
            feuille_stats.cell(row=r, column=1, value=ligne.get("colonne"))
            feuille_stats.cell(row=r, column=2, value=str(ligne.get("valeur")))
            feuille_stats.cell(row=r, column=3, value=ligne.get("effectif"))
        for idx, largeur in enumerate((28, 28, 14), start=1):
            feuille_stats.column_dimensions[get_column_letter(idx)].width = largeur
        feuille_stats.freeze_panes = "A2"

    tampon = io.BytesIO()
    classeur.save(tampon)
    return tampon.getvalue()
