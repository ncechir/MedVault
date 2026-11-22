"""Génération des notifications adressées aux demandeurs (MED-8, MED-9)."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Notification, TypeNotification


def creer(
    db: Session,
    destinataire_id: int,
    type_: TypeNotification,
    titre: str,
    message: str,
    demande_id: int | None = None,
    autorisation_id: int | None = None,
    unique: bool = False,
) -> Notification | None:
    """Crée une notification.

    `unique=True` empêche les doublons : la tâche d'échéance tourne tous les
    jours, le préavis ne doit partir qu'une seule fois par autorisation.
    """
    if unique and autorisation_id is not None:
        deja = db.scalar(
            select(Notification).where(
                Notification.autorisation_id == autorisation_id,
                Notification.type == type_,
            )
        )
        if deja:
            return None

    notification = Notification(
        destinataire_id=destinataire_id,
        type=type_,
        titre=titre,
        message=message,
        demande_id=demande_id,
        autorisation_id=autorisation_id,
    )
    db.add(notification)
    return notification
