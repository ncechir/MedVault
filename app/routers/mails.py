"""Historique des e-mails rédigés par la plateforme (réservé à l'administrateur).

Sans serveur SMTP configuré, aucun message n'est réellement envoyé ; cette
liste permet néanmoins de vérifier qu'une confirmation d'identité, une
notification de décision ou une attestation a bien été générée.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import exiger_role
from app.models import EmailEnvoye, Role
from app.schemas import EmailOut

router = APIRouter(
    prefix="/mails", tags=["E-mails"],
    dependencies=[Depends(exiger_role(Role.ADMIN))],
)


@router.get("", response_model=list[EmailOut])
def lister(
    limite: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    return db.scalars(
        select(EmailEnvoye).order_by(EmailEnvoye.cree_le.desc()).limit(limite)
    ).all()
