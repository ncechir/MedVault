import json

from sqlalchemy.orm import Session

from app.models import JournalAudit, Utilisateur


def journaliser(
    db: Session,
    utilisateur: Utilisateur | None,
    action: str,
    entite: str,
    entite_id: int | None = None,
    **details,
) -> JournalAudit:
    """Écrit une entrée d'audit. Appelé à chaque transition d'état."""
    entree = JournalAudit(
        utilisateur_id=utilisateur.id if utilisateur else None,
        utilisateur_email=utilisateur.email if utilisateur else "systeme",
        action=action,
        entite=entite,
        entite_id=entite_id,
        details=json.dumps(details, ensure_ascii=False, default=str),
    )
    db.add(entree)
    return entree
