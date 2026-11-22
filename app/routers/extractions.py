import csv
import io
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app import controle_export, excel_export, extraction
from app.audit import journaliser
from app.database import get_db
from app.dependencies import exiger_role
from app.models import Demande, Role, StatutAutorisation, Utilisateur
from app.schemas import ExtractionOut

router = APIRouter(prefix="/extractions", tags=["Extractions"])

# Le demandeur lit sa propre extraction tant que l'accès est ouvert ; le
# délégué à la protection des données dispose d'un accès de supervision à
# toutes les extractions déjà autorisées, pour contrôler ce qui est
# effectivement consulté. L'administrateur ne lit jamais de données.
LECTEURS = exiger_role(Role.CHERCHEUR, Role.DPO)


def _autoriser(db: Session, demande_id: int, user: Utilisateur) -> tuple[Demande, bool]:
    """Vérifie qu'un accès effectif existe, ici et maintenant.

    Le demandeur doit disposer d'une autorisation ACTIVE et être dans la
    fenêtre de dates. Le délégué à la protection des données supervise :
    il peut consulter toute extraction déjà autorisée, sans limite de
    fenêtre, pour vérifier ce qui est accordé — ce n'est pas un accès de
    recherche, et c'est journalisé distinctement.
    """
    demande = db.get(Demande, demande_id)
    if not demande:
        raise HTTPException(404, "Demande introuvable")

    if user.role == Role.DPO:
        if not demande.autorisation:
            raise HTTPException(403, "Aucun accès n'a été accordé pour cette demande")
        return demande, True

    if demande.demandeur_id != user.id:
        raise HTTPException(404, "Demande introuvable")

    autorisation = demande.autorisation
    if not autorisation:
        raise HTTPException(403, "Aucun accès n'a été accordé pour cette demande")
    if autorisation.statut != StatutAutorisation.ACTIVE:
        raise HTTPException(
            403, f"L'accès n'est plus ouvert (statut : {autorisation.statut.value})"
        )
    if not (autorisation.date_debut <= date.today() <= autorisation.date_fin):
        raise HTTPException(403, "Hors de la période d'accès autorisée")

    return demande, False


@router.get("/{demande_id}", response_model=ExtractionOut)
def consulter(
    demande_id: int,
    limite: int = Query(extraction.LIMITE_PAR_DEFAUT, ge=1,
                        le=extraction.LIMITE_MAX),
    db: Session = Depends(get_db),
    user: Utilisateur = Depends(LECTEURS),
):
    """Extraction des données, protections réellement appliquées."""
    demande, supervision = _autoriser(db, demande_id, user)
    try:
        resultat = extraction.produire(db, demande, limite)
    except extraction.ExtractionRefusee as erreur:
        journaliser(db, user, "EXTRACTION_REFUSEE", "demande", demande_id,
                    raison=str(erreur))
        db.commit()
        raise HTTPException(409, str(erreur))

    resultat = controle_export.appliquer(db, resultat, export=False)
    controle = resultat["controle"]

    journaliser(db, user, "EXTRACTION_CONSULTEE_DPO" if supervision else "EXTRACTION_CONSULTEE",
                "demande", demande_id,
                nb_lignes=resultat["nb_lignes"],
                colonnes=[c["code"] for c in resultat["colonnes"]],
                risque=controle["niveau"], score=controle["score"])
    db.commit()
    return resultat


@router.get("/{demande_id}/export")
def exporter(
    demande_id: int,
    limite: int = Query(extraction.LIMITE_MAX, ge=1, le=extraction.LIMITE_MAX),
    format: str = Query("csv", pattern="^(csv|xlsx)$"),
    db: Session = Depends(get_db),
    user: Utilisateur = Depends(LECTEURS),
):
    """Même extraction, au format CSV ou Excel."""
    demande, supervision = _autoriser(db, demande_id, user)
    try:
        resultat = extraction.produire(db, demande, limite)
    except extraction.ExtractionRefusee as erreur:
        raise HTTPException(409, str(erreur))

    try:
        resultat = controle_export.appliquer(db, resultat, export=True)
    except controle_export.ExportBloque as blocage:
        journaliser(db, user, "EXPORT_BLOQUE_POLITIQUE", "demande", demande_id,
                    raison=str(blocage), score=blocage.controle["score"],
                    k_min=blocage.controle["k_min"])
        db.commit()
        raise HTTPException(409, str(blocage))
    controle = resultat["controle"]

    journaliser(db, user, "EXTRACTION_EXPORTEE_DPO" if supervision else "EXTRACTION_EXPORTEE",
                "demande", demande_id,
                nb_lignes=resultat["nb_lignes"], format=format,
                risque=controle["niveau"], score=controle["score"],
                lignes_retirees=controle["nb_lignes_supprimees"],
                politique=controle["politique"])
    db.commit()

    horodatage = datetime.now().strftime("%Y%m%d-%H%M")

    if format == "xlsx":
        contenu = excel_export.construire(resultat)
        return Response(
            content=contenu,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition":
                     f'attachment; filename="extraction-{demande_id}-{horodatage}.xlsx"'},
        )

    tampon = io.StringIO()
    codes = [c["code"] for c in resultat["colonnes"]]
    ecrivain = csv.DictWriter(tampon, fieldnames=codes, delimiter=";",
                              extrasaction="ignore")
    ecrivain.writeheader()
    ecrivain.writerows(resultat["lignes"])

    return Response(
        content="﻿" + tampon.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition":
                 f'attachment; filename="extraction-{demande_id}-{horodatage}.csv"'},
    )
