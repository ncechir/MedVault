from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import utilisateur_courant
from app.models import Hopital, LotDonnees, Sejour
from app.schemas import HopitalOut, LotDetailOut, LotOut

router = APIRouter(prefix="/lots", tags=["Catalogue"],
                   dependencies=[Depends(utilisateur_courant)])


@router.get("", response_model=list[LotOut])
def lister(db: Session = Depends(get_db)):
    return db.scalars(select(LotDonnees).order_by(LotDonnees.id)).all()


@router.get("/{lot_id}", response_model=LotDetailOut)
def detail(lot_id: int, db: Session = Depends(get_db)):
    lot = db.get(LotDonnees, lot_id)
    if not lot:
        raise HTTPException(404, "Lot de données introuvable")

    services: list[str] = []
    if lot.source_donnees == "SEJOUR":
        services = ([lot.service_source] if lot.service_source
                    else sorted(db.scalars(select(Sejour.service).distinct()).all()))

    hopitaux: list[Hopital] = []
    if lot.source_donnees in ("SEJOUR", "INDICATEUR"):
        hopitaux = db.scalars(select(Hopital).order_by(Hopital.region, Hopital.nom)).all()

    sortie = LotDetailOut.model_validate(lot)
    sortie.services = services
    sortie.hopitaux = [HopitalOut.model_validate(h) for h in hopitaux]
    return sortie
