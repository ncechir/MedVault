from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import attestation, notifications, taches
from app.audit import journaliser
from app.config import DELAI_PREAVIS_JOURS
from app.database import get_db
from app.dependencies import exiger_role, utilisateur_courant
from app.models import (
    Autorisation, Demande, Role, StatutAutorisation, TypeNotification, Utilisateur,
    maintenant,
)
from app.schemas import AutorisationOut, EcheanceOut, ResumeTacheOut, RevocationIn

router = APIRouter(prefix="/autorisations", tags=["Autorisations"])


@router.get("", response_model=list[AutorisationOut])
def lister(
    statut: StatutAutorisation | None = None,
    db: Session = Depends(get_db),
    user: Utilisateur = Depends(utilisateur_courant),
):
    requete = select(Autorisation).join(Demande).order_by(Autorisation.date_fin)
    if user.role == Role.CHERCHEUR:
        requete = requete.where(Demande.demandeur_id == user.id)
    if statut:
        requete = requete.where(Autorisation.statut == statut)
    return db.scalars(requete).all()


@router.get("/echeances", response_model=list[EcheanceOut])
def echeances(
    jours: int = DELAI_PREAVIS_JOURS,
    db: Session = Depends(get_db),
    user: Utilisateur = Depends(utilisateur_courant),
):
    """Accès arrivant à terme dans les prochains jours (MED-8)."""
    limite = date.today() + timedelta(days=jours)
    requete = (
        select(Autorisation).join(Demande)
        .where(
            Autorisation.statut == StatutAutorisation.ACTIVE,
            Autorisation.date_fin <= limite,
            Autorisation.date_fin >= date.today(),
        )
        .order_by(Autorisation.date_fin)
    )
    if user.role == Role.CHERCHEUR:
        requete = requete.where(Demande.demandeur_id == user.id)

    return [
        EcheanceOut(
            autorisation=a,
            titre_projet=a.demande.titre_projet,
            demandeur=a.demande.demandeur.nom_complet,
            jours_restants=(a.date_fin - date.today()).days,
        )
        for a in db.scalars(requete).all()
    ]


@router.get("/{autorisation_id}/attestation")
def telecharger_attestation(
    autorisation_id: int,
    db: Session = Depends(get_db),
    user: Utilisateur = Depends(utilisateur_courant),
):
    """Régénère le document attestant l'autorisation, à l'identique de celui
    envoyé par e-mail au moment de la décision."""
    autorisation = db.get(Autorisation, autorisation_id)
    if not autorisation:
        raise HTTPException(404, "Autorisation introuvable")
    demande = autorisation.demande
    if user.role == Role.CHERCHEUR and demande.demandeur_id != user.id:
        raise HTTPException(404, "Autorisation introuvable")
    decision = autorisation.decision
    if not decision:
        raise HTTPException(404, "Aucune décision associée à cette autorisation")

    pdf = attestation.generer(
        reference=demande.reference, titre_projet=demande.titre_projet,
        finalite=demande.finalite, demandeur_nom=demande.demandeur.nom_complet,
        demandeur_service=demande.demandeur.service, dpo_nom=decision.dpo.nom_complet,
        motif=decision.motif, conditions=decision.conditions,
        date_debut=autorisation.date_debut, date_fin=autorisation.date_fin,
        date_purge=autorisation.date_purge_prevue,
        colonnes=[dc.champ.libelle for dc in demande.champs_demandes],
        services=demande.services, prise_le=decision.prise_le,
    )
    journaliser(db, user, "ATTESTATION_TELECHARGEE", "autorisation", autorisation.id)
    db.commit()
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition":
                 f'attachment; filename="attestation-{demande.reference}.pdf"'},
    )


@router.post("/{autorisation_id}/revoquer", response_model=AutorisationOut)
def revoquer(
    autorisation_id: int,
    payload: RevocationIn,
    db: Session = Depends(get_db),
    user: Utilisateur = Depends(exiger_role(Role.DPO)),
):
    autorisation = db.get(Autorisation, autorisation_id)
    if not autorisation:
        raise HTTPException(404, "Autorisation introuvable")
    if autorisation.statut != StatutAutorisation.ACTIVE:
        raise HTTPException(409, "Seule une autorisation ACTIVE peut être révoquée")

    autorisation.statut = StatutAutorisation.REVOQUEE
    autorisation.revoquee_le = maintenant()
    autorisation.motif_revocation = payload.motif
    notifications.creer(
        db, autorisation.demande.demandeur_id, TypeNotification.ACCES_REVOQUE,
        f"Accès révoqué — {autorisation.demande.titre_projet}",
        f"L'accès a été interrompu avant son terme. Motif : {payload.motif}",
        demande_id=autorisation.demande_id, autorisation_id=autorisation.id,
    )
    journaliser(db, user, "ACCES_REVOQUE", "autorisation", autorisation.id,
                motif=payload.motif)
    db.commit()
    db.refresh(autorisation)
    return autorisation


@router.post("/{autorisation_id}/purger", response_model=AutorisationOut)
def purger(
    autorisation_id: int,
    db: Session = Depends(get_db),
    user: Utilisateur = Depends(exiger_role(Role.DPO, Role.ADMIN)),
):
    """Atteste de la suppression effective de l'extraction remise au chercheur."""
    autorisation = db.get(Autorisation, autorisation_id)
    if not autorisation:
        raise HTTPException(404, "Autorisation introuvable")
    if autorisation.statut not in (
        StatutAutorisation.EXPIREE, StatutAutorisation.REVOQUEE
    ):
        raise HTTPException(409, "L'accès doit être expiré ou révoqué avant purge")

    autorisation.statut = StatutAutorisation.PURGEE
    autorisation.purge_effectuee_le = maintenant()
    journaliser(db, user, "DONNEES_PURGEES", "autorisation", autorisation.id)
    db.commit()
    db.refresh(autorisation)
    return autorisation


@router.post("/taches/expiration", response_model=ResumeTacheOut)
def passer_les_expirations(
    db: Session = Depends(get_db),
    user: Utilisateur = Depends(exiger_role(Role.ADMIN, Role.DPO)),
):
    """Déclenche manuellement la tâche quotidienne d'échéances (MED-8, MED-16).

    Le planificateur exécute la même fonction chaque nuit ; cet endpoint sert
    aux démonstrations et au rattrapage après une interruption du service.
    """
    return taches.executer_echeances(db, user)
