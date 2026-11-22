"""Gestion des comptes : le rôle concret de l'administrateur.

L'administrateur ouvre, désactive ou change le rôle d'un compte. Il ne décide
d'aucun accès aux données et n'en lit aucune : ces pouvoirs appartiennent au
responsable des données.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit import journaliser
from app.database import get_db
from app.dependencies import exiger_role
from app.models import Decision, Demande, Role, Utilisateur
from app.schemas import UtilisateurAdminOut, UtilisateurMaj

router = APIRouter(prefix="/utilisateurs", tags=["Comptes"])


def _vue(u: Utilisateur, nb_demandes: int) -> UtilisateurAdminOut:
    return UtilisateurAdminOut(
        id=u.id, email=u.email, nom_complet=u.nom_complet, service=u.service,
        role=u.role, actif=u.actif, cree_le=u.cree_le, nb_demandes=nb_demandes,
    )


def _nb_demandes(db: Session) -> dict[int, int]:
    return dict(db.execute(
        select(Demande.demandeur_id, func.count(Demande.id))
        .group_by(Demande.demandeur_id)
    ).all())


@router.get("", response_model=list[UtilisateurAdminOut])
def lister(
    db: Session = Depends(get_db),
    _admin: Utilisateur = Depends(exiger_role(Role.ADMIN)),
):
    comptes = _nb_demandes(db)
    utilisateurs = db.scalars(
        select(Utilisateur).order_by(Utilisateur.cree_le.desc(), Utilisateur.id.desc())
    ).all()
    return [_vue(u, comptes.get(u.id, 0)) for u in utilisateurs]


@router.patch("/{utilisateur_id}", response_model=UtilisateurAdminOut)
def modifier(
    utilisateur_id: int,
    payload: UtilisateurMaj,
    db: Session = Depends(get_db),
    admin: Utilisateur = Depends(exiger_role(Role.ADMIN)),
):
    cible = db.get(Utilisateur, utilisateur_id)
    if not cible:
        raise HTTPException(404, "Compte introuvable")
    if cible.id == admin.id:
        # Sinon un administrateur pourrait se retirer ses propres droits et
        # laisser la plateforme sans personne pour gérer les comptes.
        raise HTTPException(409, "Vous ne pouvez pas modifier votre propre compte.")

    changements = {}
    if payload.role is not None and payload.role != cible.role:
        changements["role"] = f"{cible.role.value} -> {payload.role.value}"
        cible.role = payload.role
    if payload.actif is not None and payload.actif != cible.actif:
        changements["actif"] = payload.actif
        cible.actif = payload.actif

    if changements:
        journaliser(db, admin, "COMPTE_MODIFIE", "utilisateur", cible.id,
                    compte=cible.email, **changements)
        db.commit()
        db.refresh(cible)
    return _vue(cible, _nb_demandes(db).get(cible.id, 0))


@router.delete("/{utilisateur_id}", status_code=status.HTTP_204_NO_CONTENT)
def supprimer(
    utilisateur_id: int,
    confirmation: str = Query(..., description="Adresse e-mail du compte, pour confirmation"),
    db: Session = Depends(get_db),
    admin: Utilisateur = Depends(exiger_role(Role.ADMIN)),
):
    """Suppression définitive d'un compte.

    Double confirmation côté interface : l'administrateur doit retaper
    l'adresse e-mail exacte du compte à supprimer. Un compte ayant déjà une
    activité (demande ou décision) n'est pas supprimable — il doit être
    désactivé plutôt que supprimé, pour garder la trace de ce qui s'est passé.
    """
    cible = db.get(Utilisateur, utilisateur_id)
    if not cible:
        raise HTTPException(404, "Compte introuvable")
    if cible.id == admin.id:
        raise HTTPException(409, "Vous ne pouvez pas supprimer votre propre compte.")
    if confirmation.strip().lower() != cible.email.lower():
        raise HTTPException(400, "L'adresse e-mail saisie ne correspond pas au compte.")

    a_une_activite = db.scalar(
        select(Demande.id).where(Demande.demandeur_id == cible.id).limit(1)
    ) or db.scalar(
        select(Decision.id).where(Decision.dpo_id == cible.id).limit(1)
    )
    if a_une_activite:
        raise HTTPException(
            409, "Ce compte a déjà une activité enregistrée : désactivez-le plutôt "
                 "que de le supprimer, afin de conserver la trace des décisions prises."
        )

    journaliser(db, admin, "COMPTE_SUPPRIME", "utilisateur", cible.id, compte=cible.email)
    db.delete(cible)
    db.commit()
    return None
