from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import utilisateur_courant
from app.models import Notification, Utilisateur
from app.schemas import NotificationOut

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("", response_model=list[NotificationOut])
def lister(
    non_lues: bool = False,
    db: Session = Depends(get_db),
    user: Utilisateur = Depends(utilisateur_courant),
):
    """Chacun ne voit que ses propres notifications."""
    requete = (
        select(Notification)
        .where(Notification.destinataire_id == user.id)
        .order_by(Notification.cree_le.desc())
    )
    if non_lues:
        requete = requete.where(Notification.lue.is_(False))
    return db.scalars(requete).all()


@router.get("/compte")
def compter_non_lues(
    db: Session = Depends(get_db),
    user: Utilisateur = Depends(utilisateur_courant),
):
    total = db.scalar(
        select(func.count(Notification.id)).where(
            Notification.destinataire_id == user.id,
            Notification.lue.is_(False),
        )
    )
    return {"non_lues": total or 0}


@router.post("/{notification_id}/lue", response_model=NotificationOut)
def marquer_lue(
    notification_id: int,
    db: Session = Depends(get_db),
    user: Utilisateur = Depends(utilisateur_courant),
):
    notification = db.get(Notification, notification_id)
    if not notification or notification.destinataire_id != user.id:
        raise HTTPException(404, "Notification introuvable")
    notification.lue = True
    db.commit()
    db.refresh(notification)
    return notification
