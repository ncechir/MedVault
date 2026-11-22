import csv
import io
import json
from datetime import date, datetime

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import journaliser
from app.database import get_db
from app.dependencies import exiger_role
from app.models import JournalAudit, Role, Utilisateur
from app.schemas import AuditOut

router = APIRouter(prefix="/journal", tags=["Traçabilité"])

PILOTES = exiger_role(Role.ADMIN)


def _filtrer(requete, action, entite, debut, fin):
    if action:
        requete = requete.where(JournalAudit.action == action)
    if entite:
        requete = requete.where(JournalAudit.entite == entite)
    if debut:
        requete = requete.where(
            JournalAudit.horodatage >= datetime.combine(debut, datetime.min.time()))
    if fin:
        requete = requete.where(
            JournalAudit.horodatage <= datetime.combine(fin, datetime.max.time()))
    return requete


@router.get("", response_model=list[AuditOut], dependencies=[Depends(PILOTES)])
def lister(
    action: str | None = None,
    entite: str | None = None,
    debut: date | None = None,
    fin: date | None = None,
    limite: int = 200,
    db: Session = Depends(get_db),
):
    requete = _filtrer(
        select(JournalAudit).order_by(JournalAudit.horodatage.desc()),
        action, entite, debut, fin,
    )
    return db.scalars(requete.limit(limite)).all()


@router.get("/actions", response_model=list[str], dependencies=[Depends(PILOTES)])
def actions_disponibles(db: Session = Depends(get_db)):
    """Alimente les filtres de l'interface sans coder la liste en dur."""
    return sorted(db.scalars(select(JournalAudit.action).distinct()).all())


@router.get("/export")
def exporter(
    format: str = Query("csv", pattern="^(csv|json)$"),
    action: str | None = None,
    entite: str | None = None,
    debut: date | None = None,
    fin: date | None = None,
    db: Session = Depends(get_db),
    user: Utilisateur = Depends(PILOTES),
):
    """Export du journal d'audit (MED-18).

    L'export est lui-meme journalise : extraire le registre est un acte de
    traitement, il doit laisser une trace comme les autres.
    """
    requete = _filtrer(
        select(JournalAudit).order_by(JournalAudit.horodatage.asc()),
        action, entite, debut, fin,
    )
    entrees = db.scalars(requete).all()

    journaliser(db, user, "JOURNAL_EXPORTE", "journal_audit",
                nb_entrees=len(entrees), format=format,
                filtres={"action": action, "entite": entite,
                         "debut": str(debut), "fin": str(fin)})
    db.commit()

    horodatage = datetime.now().strftime("%Y%m%d-%H%M")
    colonnes = ["id", "horodatage", "utilisateur_email", "action",
                "entite", "entite_id", "details"]

    if format == "json":
        contenu = json.dumps(
            [{c: (e.horodatage.isoformat() if c == "horodatage" else getattr(e, c))
              for c in colonnes} for e in entrees],
            ensure_ascii=False, indent=2, default=str,
        )
        return Response(
            content=contenu, media_type="application/json",
            headers={"Content-Disposition":
                     f'attachment; filename="journal-{horodatage}.json"'},
        )

    tampon = io.StringIO()
    ecrivain = csv.writer(tampon, delimiter=";")
    ecrivain.writerow(colonnes)
    for e in entrees:
        ecrivain.writerow([
            e.id, e.horodatage.isoformat(), e.utilisateur_email,
            e.action, e.entite, e.entite_id or "", e.details,
        ])

    return Response(
        content="\ufeff" + tampon.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition":
                 f'attachment; filename="journal-{horodatage}.csv"'},
    )
