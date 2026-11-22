"""Établissements du territoire et leurs indicateurs annuels.

Lecture accessible au chercheur (pour choisir une zone à sa demande) et au
délégué (pour la supervision) ; aucune donnée de patient ici, uniquement des
statistiques déjà agrégées par établissement.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import exiger_role
from app.models import Hopital, IndicateurHopital, Role, Sejour
from app.schemas import HopitalDetailOut, HopitalOut, IndicateurAnnuelOut

router = APIRouter(
    prefix="/hopitaux", tags=["Établissements"],
    dependencies=[Depends(exiger_role(Role.CHERCHEUR, Role.DPO))],
)


def _dernier_indicateur(db: Session, code: str) -> IndicateurAnnuelOut | None:
    ligne = db.scalar(
        select(IndicateurHopital)
        .where(IndicateurHopital.hopital_code == code)
        .order_by(IndicateurHopital.annee.desc())
        .limit(1)
    )
    return IndicateurAnnuelOut.model_validate(ligne) if ligne else None


@router.get("", response_model=list[HopitalOut])
def lister(db: Session = Depends(get_db)):
    hopitaux = db.scalars(select(Hopital).order_by(Hopital.region, Hopital.nom)).all()
    comptes = dict(db.execute(
        select(Sejour.hopital_code, func.count(Sejour.id)).group_by(Sejour.hopital_code)
    ).all())
    sortie = []
    for h in hopitaux:
        vue = HopitalOut.model_validate(h)
        vue.nb_sejours = comptes.get(h.code, 0)
        vue.dernier_indicateur = _dernier_indicateur(db, h.code)
        sortie.append(vue)
    return sortie


@router.get("/{hopital_id}", response_model=HopitalDetailOut)
def detail(hopital_id: int, db: Session = Depends(get_db)):
    h = db.get(Hopital, hopital_id)
    if not h:
        raise HTTPException(404, "Établissement introuvable")
    nb_sejours = db.scalar(
        select(func.count(Sejour.id)).where(Sejour.hopital_code == h.code)
    ) or 0
    historique = db.scalars(
        select(IndicateurHopital)
        .where(IndicateurHopital.hopital_code == h.code)
        .order_by(IndicateurHopital.annee)
    ).all()
    sortie = HopitalDetailOut.model_validate(h)
    sortie.nb_sejours = nb_sejours
    sortie.dernier_indicateur = (
        IndicateurAnnuelOut.model_validate(historique[-1]) if historique else None
    )
    sortie.historique = [IndicateurAnnuelOut.model_validate(l) for l in historique]
    return sortie
