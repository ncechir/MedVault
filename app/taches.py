"""Tâches planifiées du cycle de vie des accès (MED-8, MED-16).

Ce module ne dépend ni de FastAPI ni d'une requête HTTP : il est appelé
aussi bien par l'endpoint d'administration que par le planificateur.
"""
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import notifications
from app.audit import journaliser
from app.config import DELAI_PREAVIS_JOURS, DELAI_PURGE_JOURS
from app.models import (
    Autorisation, StatutAutorisation, TypeNotification, Utilisateur, maintenant,
)


def envoyer_preavis(db: Session, acteur: Utilisateur | None) -> int:
    """Prévient les titulaires d'un accès arrivant à terme (MED-8)."""
    limite = date.today() + timedelta(days=DELAI_PREAVIS_JOURS)
    a_venir = db.scalars(
        select(Autorisation).where(
            Autorisation.statut == StatutAutorisation.ACTIVE,
            Autorisation.date_fin <= limite,
            Autorisation.date_fin >= date.today(),
        )
    ).all()

    envoyes = 0
    for autorisation in a_venir:
        restants = (autorisation.date_fin - date.today()).days
        cree = notifications.creer(
            db, autorisation.demande.demandeur_id,
            TypeNotification.ACCES_BIENTOT_EXPIRE,
            f"Accès bientôt clos — {autorisation.demande.titre_projet}",
            f"Il vous reste {restants} jour(s). À l'échéance du "
            f"{autorisation.date_fin.strftime('%d/%m/%Y')}, l'accès sera coupé et "
            "l'extraction en votre possession devra être supprimée.",
            demande_id=autorisation.demande_id, autorisation_id=autorisation.id,
            unique=True,
        )
        if cree:
            envoyes += 1
            journaliser(db, acteur, "PREAVIS_EXPIRATION", "autorisation",
                        autorisation.id, jours_restants=restants)
    return envoyes


def cloturer_les_echus(db: Session, acteur: Utilisateur | None) -> list[Autorisation]:
    """Coupe les accès arrivés à terme."""
    echues = db.scalars(
        select(Autorisation).where(
            Autorisation.statut == StatutAutorisation.ACTIVE,
            Autorisation.date_fin < date.today(),
        )
    ).all()

    for autorisation in echues:
        autorisation.statut = StatutAutorisation.EXPIREE
        notifications.creer(
            db, autorisation.demande.demandeur_id, TypeNotification.ACCES_EXPIRE,
            f"Accès clos — {autorisation.demande.titre_projet}",
            f"L'accès est arrivé à son terme. Les données seront supprimées "
            f"d'office sous {DELAI_PURGE_JOURS} jours.",
            demande_id=autorisation.demande_id, autorisation_id=autorisation.id,
        )
        journaliser(db, acteur, "ACCES_EXPIRE", "autorisation", autorisation.id,
                    date_fin=autorisation.date_fin)
    return echues


def purger_doffice(db: Session, acteur: Utilisateur | None) -> int:
    """Supprime les extractions dont l'accès est clos depuis assez longtemps (MED-16).

    Sans cette étape, une donnée expirée resterait indéfiniment en attente d'un
    geste manuel du DPO — exactement le risque que le projet cherche à supprimer.
    """
    seuil = date.today() - timedelta(days=DELAI_PURGE_JOURS)
    candidates = db.scalars(
        select(Autorisation).where(
            Autorisation.statut.in_(
                [StatutAutorisation.EXPIREE, StatutAutorisation.REVOQUEE]
            ),
            Autorisation.date_fin <= seuil,
        )
    ).all()

    for autorisation in candidates:
        autorisation.statut = StatutAutorisation.PURGEE
        autorisation.purge_effectuee_le = maintenant()
        journaliser(db, acteur, "PURGE_AUTOMATIQUE", "autorisation", autorisation.id,
                    date_fin=autorisation.date_fin, delai_jours=DELAI_PURGE_JOURS)
    return len(candidates)


def executer_echeances(db: Session, acteur: Utilisateur | None = None) -> dict:
    """Enchaîne les trois étapes. Idempotente : rejouable sans effet de bord."""
    preavis = envoyer_preavis(db, acteur)
    clotures = cloturer_les_echus(db, acteur)
    # Les sessions sont en autoflush=False : sans ce flush, la purge ne verrait
    # pas les accès que l'étape précédente vient de passer en EXPIREE.
    db.flush()
    purges = purger_doffice(db, acteur)
    db.commit()
    return {
        "preavis_envoyes": preavis,
        "acces_clotures": clotures,
        "donnees_purgees": purges,
    }
