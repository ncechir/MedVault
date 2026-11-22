"""Support : échanges entre les chercheurs et l'administrateur.

Un chercheur ouvre un ticket (question, problème, demande de suppression d'un
dossier) ; l'administrateur répond. Chacun ne voit que ses propres tickets,
l'administrateur les voit tous. Aucune donnée de santé n'a sa place ici.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit import journaliser
from app.database import get_db
from app.dependencies import exiger_role, utilisateur_courant
from app.models import MessageSupport, Role, TicketSupport, Utilisateur, maintenant
from app.schemas import MessageIn, StatutTicketIn, TicketIn, TicketOut

router = APIRouter(prefix="/support", tags=["Support"])


def _ticket_visible(db: Session, ticket_id: int, user: Utilisateur) -> TicketSupport:
    ticket = db.get(TicketSupport, ticket_id)
    if not ticket or (user.role != Role.ADMIN and ticket.auteur_id != user.id):
        raise HTTPException(404, "Ticket introuvable")
    return ticket


@router.get("/tickets", response_model=list[TicketOut])
def lister(
    db: Session = Depends(get_db),
    user: Utilisateur = Depends(exiger_role(Role.CHERCHEUR, Role.ADMIN)),
):
    requete = select(TicketSupport).order_by(TicketSupport.maj_le.desc())
    if user.role != Role.ADMIN:
        requete = requete.where(TicketSupport.auteur_id == user.id)
    return db.scalars(requete).all()


@router.get("/a-traiter")
def a_traiter(
    db: Session = Depends(get_db),
    user: Utilisateur = Depends(exiger_role(Role.CHERCHEUR, Role.ADMIN)),
):
    """Nombre de tickets ouverts dont le dernier message attend une réponse de
    l'administrateur (côté admin) ou du chercheur (côté chercheur)."""
    requete = select(TicketSupport).where(TicketSupport.statut == "OUVERT")
    if user.role != Role.ADMIN:
        requete = requete.where(TicketSupport.auteur_id == user.id)
    n = 0
    for t in db.scalars(requete):
        dernier = t.messages[-1].auteur if t.messages else None
        if dernier is None:
            continue
        if user.role == Role.ADMIN and dernier.role != Role.ADMIN:
            n += 1
        if user.role != Role.ADMIN and dernier.role == Role.ADMIN:
            n += 1
    return {"a_traiter": n}


@router.post("/tickets", response_model=TicketOut, status_code=201)
def ouvrir(
    payload: TicketIn,
    db: Session = Depends(get_db),
    user: Utilisateur = Depends(exiger_role(Role.CHERCHEUR)),
):
    ticket = TicketSupport(
        auteur_id=user.id, categorie=payload.categorie, sujet=payload.sujet.strip(),
    )
    ticket.messages.append(MessageSupport(auteur_id=user.id, corps=payload.message.strip()))
    db.add(ticket)
    db.flush()
    journaliser(db, user, "SUPPORT_TICKET_OUVERT", "ticket_support", ticket.id,
                categorie=payload.categorie)
    db.commit()
    db.refresh(ticket)
    return ticket


@router.post("/tickets/{ticket_id}/messages", response_model=TicketOut)
def repondre(
    ticket_id: int,
    payload: MessageIn,
    db: Session = Depends(get_db),
    user: Utilisateur = Depends(exiger_role(Role.CHERCHEUR, Role.ADMIN)),
):
    ticket = _ticket_visible(db, ticket_id, user)
    ticket.messages.append(MessageSupport(auteur_id=user.id, corps=payload.message.strip()))
    ticket.maj_le = maintenant()
    if user.role != Role.ADMIN:
        ticket.statut = "OUVERT"  # un nouveau message du chercheur rouvre l'échange
    journaliser(db, user, "SUPPORT_MESSAGE", "ticket_support", ticket.id)
    db.commit()
    db.refresh(ticket)
    return ticket


@router.post("/tickets/{ticket_id}/statut", response_model=TicketOut)
def changer_statut(
    ticket_id: int,
    payload: StatutTicketIn,
    db: Session = Depends(get_db),
    user: Utilisateur = Depends(exiger_role(Role.ADMIN)),
):
    ticket = _ticket_visible(db, ticket_id, user)
    ticket.statut = payload.statut
    ticket.maj_le = maintenant()
    journaliser(db, user, "SUPPORT_STATUT", "ticket_support", ticket.id, statut=payload.statut)
    db.commit()
    db.refresh(ticket)
    return ticket
