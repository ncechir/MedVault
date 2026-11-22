"""Import, par le délégué, d'un jeu de données complet au format CSV.

Chaque colonne du fichier devient un champ du catalogue, sous la catégorie
RGPD choisie par le délégué pour l'ensemble du fichier (un fichier n'est pas
un mélange : soit il décrit des personnes, soit il ne le fait pas — c'est au
délégué de le qualifier avant publication). Les lignes sont conservées
telles quelles, en JSON, pour s'adapter à n'importe quelle forme de fichier.
"""
import csv
import io
import json
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit import journaliser
from app.database import get_db
from app.dependencies import exiger_role
from app.models import (
    CategorieChamp, Champ, Demande, LigneGenerique, LotDonnees, Role, Utilisateur,
    maintenant,
)
from app.schemas import ImportLotOut

router = APIRouter(
    prefix="/import", tags=["Import de données"],
    dependencies=[Depends(exiger_role(Role.DPO))],
)

LIMITE_LIGNES = 20_000
LIMITE_OCTETS = 15 * 1024 * 1024


def _lot_vers_sortie(lot: LotDonnees, nb_lignes: int) -> ImportLotOut:
    categorie = lot.champs[0].categorie.value if lot.champs else ""
    return ImportLotOut(
        id=lot.id, code=lot.code, libelle=lot.libelle, description=lot.description,
        categorie=categorie, nb_lignes=nb_lignes,
        importe_par=lot.importe_par.nom_complet if lot.importe_par else "",
        importe_le=lot.importe_le,
    )


@router.get("", response_model=list[ImportLotOut])
def lister(db: Session = Depends(get_db)):
    lots = db.scalars(
        select(LotDonnees).where(LotDonnees.source_donnees == "GENERIQUE")
        .order_by(LotDonnees.importe_le.desc())
    ).all()
    sortie = []
    for lot in lots:
        nb = db.scalar(
            select(func.count(LigneGenerique.id)).where(LigneGenerique.lot_id == lot.id)
        ) or 0
        sortie.append(_lot_vers_sortie(lot, nb))
    return sortie


def _code_colonne(nom: str, deja_vus: set[str]) -> str:
    base = "".join(c if c.isalnum() else "_" for c in nom.strip().lower()).strip("_") or "colonne"
    code, i = base, 1
    while code in deja_vus:
        i += 1
        code = f"{base}_{i}"
    deja_vus.add(code)
    return code


@router.post("", response_model=ImportLotOut, status_code=201)
async def importer(
    libelle: str = Form(..., min_length=3, max_length=200),
    description: str = Form(""),
    categorie: CategorieChamp = Form(...),
    fichier: UploadFile = File(...),
    db: Session = Depends(get_db),
    dpo: Utilisateur = Depends(exiger_role(Role.DPO)),
):
    if not (fichier.filename or "").lower().endswith(".csv"):
        raise HTTPException(400, "Seuls les fichiers CSV sont acceptés.")
    contenu = await fichier.read()
    if len(contenu) > LIMITE_OCTETS:
        raise HTTPException(400, "Fichier trop volumineux (15 Mo maximum).")

    texte = contenu.decode("utf-8-sig", errors="replace")
    echantillon = texte[:4096]
    delimiteur = ";" if echantillon.count(";") >= echantillon.count(",") else ","
    lecteur = csv.reader(io.StringIO(texte), delimiter=delimiteur)
    try:
        entetes = next(lecteur)
    except StopIteration:
        raise HTTPException(400, "Fichier CSV vide.")

    deja_vus: set[str] = set()
    colonnes = [(nom.strip() or f"colonne_{i+1}", _code_colonne(nom, deja_vus))
                for i, nom in enumerate(entetes)]

    lignes_json = []
    for ligne in lecteur:
        if not any(c.strip() for c in ligne):
            continue
        objet = {colonnes[i][1]: (ligne[i].strip() if i < len(ligne) else "")
                for i in range(len(colonnes))}
        lignes_json.append(objet)
        if len(lignes_json) >= LIMITE_LIGNES:
            break

    if not lignes_json:
        raise HTTPException(400, "Aucune ligne de données exploitable dans ce fichier.")

    base_code = "IMPORT_" + "".join(c if c.isalnum() else "_" for c in libelle.upper())[:30]
    code = base_code
    suffixe = 1
    while db.scalar(select(LotDonnees).where(LotDonnees.code == code)):
        suffixe += 1
        code = f"{base_code}_{suffixe}"

    lot = LotDonnees(
        code=code, libelle=libelle.strip(), description=description.strip(),
        responsable=dpo.nom_complet, source_donnees="GENERIQUE",
        importe_par_id=dpo.id, importe_le=maintenant(),
    )
    lot.champs = [
        Champ(code=code_col, libelle=nom_col, categorie=categorie,
              source=f"generique.{code_col}", groupe="Donnée importée")
        for nom_col, code_col in colonnes
    ]
    db.add(lot)
    db.flush()
    db.add_all([LigneGenerique(lot_id=lot.id, donnees_json=json.dumps(l, ensure_ascii=False))
                for l in lignes_json])
    journaliser(db, dpo, "DONNEES_IMPORTEES", "lot_donnees", lot.id,
                libelle=lot.libelle, nb_lignes=len(lignes_json), categorie=categorie.value)
    db.commit()
    db.refresh(lot)
    return _lot_vers_sortie(lot, len(lignes_json))


@router.delete("/{lot_id}", status_code=204)
def supprimer(
    lot_id: int,
    db: Session = Depends(get_db),
    dpo: Utilisateur = Depends(exiger_role(Role.DPO)),
):
    lot = db.get(LotDonnees, lot_id)
    if not lot or lot.source_donnees != "GENERIQUE":
        raise HTTPException(404, "Jeu de données importé introuvable")
    if db.scalar(select(Demande.id).where(Demande.lot_id == lot.id).limit(1)):
        raise HTTPException(
            409, "Ce jeu de données est référencé par au moins une demande : "
                 "il ne peut plus être supprimé."
        )
    db.execute(LigneGenerique.__table__.delete().where(LigneGenerique.lot_id == lot.id))
    journaliser(db, dpo, "IMPORT_SUPPRIME", "lot_donnees", lot.id, libelle=lot.libelle)
    db.delete(lot)
    db.commit()
    return None
