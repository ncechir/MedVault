"""Suppression de demandes par l'administrateur.

L'administrateur ne lit ni le contenu ni les données d'une demande : il voit
seulement de quoi la reconnaître (référence, titre, demandeur, statut) et peut
la supprimer, par exemple à la demande de son auteur via le support. La
suppression est tracée dans le journal d'audit, qui n'est jamais modifié.
Un accès encore ouvert doit d'abord être révoqué par le responsable des données.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.audit import journaliser
from app.database import get_db
from app.dependencies import exiger_role
from app.models import (
    Demande, Notification, Role, StatutAutorisation, Utilisateur,
)
from app.schemas import Base, UTCDatetime

router = APIRouter(prefix="/admin/demandes", tags=["Administration des demandes"])


class DemandeAdminOut(Base):
    id: int
    reference: str
    titre_projet: str
    statut: str
    cree_le: UTCDatetime
    demandeur_nom: str
    demandeur_email: str
    acces_ouvert: bool


def _vue(d: Demande) -> DemandeAdminOut:
    return DemandeAdminOut(
        id=d.id, reference=d.reference, titre_projet=d.titre_projet,
        statut=d.statut.value, cree_le=d.cree_le,
        demandeur_nom=d.demandeur.nom_complet, demandeur_email=d.demandeur.email,
        acces_ouvert=bool(d.autorisation and d.autorisation.statut == StatutAutorisation.ACTIVE),
    )


@router.get("", response_model=list[DemandeAdminOut])
def lister(
    db: Session = Depends(get_db),
    admin: Utilisateur = Depends(exiger_role(Role.ADMIN)),
):
    demandes = db.scalars(select(Demande).order_by(Demande.cree_le.desc())).all()
    return [_vue(d) for d in demandes]


@router.delete("/{demande_id}", status_code=status.HTTP_204_NO_CONTENT)
def supprimer(
    demande_id: int,
    confirmation: str = Query(..., description="Référence de la demande, pour confirmation"),
    db: Session = Depends(get_db),
    admin: Utilisateur = Depends(exiger_role(Role.ADMIN)),
):
    demande = db.get(Demande, demande_id)
    if not demande:
        raise HTTPException(404, "Demande introuvable")
    if confirmation.strip().upper() != demande.reference.upper():
        raise HTTPException(400, "La référence saisie ne correspond pas à la demande.")
    if demande.autorisation and demande.autorisation.statut == StatutAutorisation.ACTIVE:
        raise HTTPException(
            409, "Un accès est encore ouvert pour cette demande : le délégué à la "
                 "protection des données doit d'abord le révoquer."
        )

    reference = demande.reference
    journaliser(db, admin, "DEMANDE_SUPPRIMEE", "demande", demande.id,
                reference=reference, statut=demande.statut.value,
                demandeur=demande.demandeur.email)
    # Les notifications pointent vers la demande et son accès : elles partent avec elle.
    ids_autorisation = [demande.autorisation.id] if demande.autorisation else []
    condition = Notification.demande_id == demande.id
    if ids_autorisation:
        condition = or_(condition, Notification.autorisation_id.in_(ids_autorisation))
    db.execute(delete(Notification).where(condition))
    db.delete(demande)
    db.commit()
    return None
