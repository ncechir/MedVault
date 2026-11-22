from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import attestation, conformite, mailer, notifications
from app.audit import journaliser
from app.database import get_db
from app.dependencies import exiger_role
from app.models import (
    Autorisation, Champ, Decision, Demande, DemandeChamp, Hopital, LotDonnees,
    Role, Sejour, SensDecision, StatutAutorisation, StatutDemande,
    TypeNotification, Utilisateur, maintenant,
)
from app.schemas import (
    DecisionIn, DecisionOut, DemandeIn, DemandeOut, DemandeUpdate, RapportConformite,
)

router = APIRouter(prefix="/demandes", tags=["Demandes"])


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
# Le demandeur dépose ; le responsable des données instruit. L'administrateur
# gère les comptes et n'a aucune raison de lire les demandes.
LECTEURS = exiger_role(Role.CHERCHEUR, Role.DPO)


def _recuperer(db: Session, demande_id: int, user: Utilisateur) -> Demande:
    """Récupère une demande en appliquant le principe du moindre privilège."""
    demande = db.get(Demande, demande_id)
    if not demande:
        raise HTTPException(404, "Demande introuvable")
    if user.role == Role.CHERCHEUR and demande.demandeur_id != user.id:
        # On ne révèle pas l'existence de la demande d'un autre demandeur
        raise HTTPException(404, "Demande introuvable")
    if user.role == Role.DPO and demande.statut == StatutDemande.BROUILLON:
        # Un brouillon n'est pas encore transmis : il reste privé
        raise HTTPException(404, "Demande introuvable")
    return demande


def _recuperer_proprietaire(db: Session, demande_id: int, user: Utilisateur) -> Demande:
    """Modifier ou transmettre une demande : réservé à la personne qui l'a déposée."""
    demande = db.get(Demande, demande_id)
    if not demande or demande.demandeur_id != user.id:
        raise HTTPException(404, "Demande introuvable")
    return demande


def _verifier_services(db: Session, lot: LotDonnees, services: list[str]) -> list[str]:
    """Ne garde que des services qui existent, sans doublon. Sans objet hors séjours."""
    if lot.source_donnees != "SEJOUR" or not services:
        return []
    autorises = ({lot.service_source} if lot.service_source
                 else set(db.scalars(select(Sejour.service).distinct()).all()))
    inconnus = [x for x in services if x not in autorises]
    if inconnus:
        raise HTTPException(400, f"Service inconnu : {', '.join(inconnus)}")
    return list(dict.fromkeys(services))


def _verifier_hopitaux(db: Session, lot: LotDonnees, hopitaux: list[str]) -> list[str]:
    """Ne garde que des établissements qui existent. Sans objet hors séjours/indicateurs."""
    if lot.source_donnees not in ("SEJOUR", "INDICATEUR") or not hopitaux:
        return []
    autorises = set(db.scalars(select(Hopital.code)).all())
    inconnus = [x for x in hopitaux if x not in autorises]
    if inconnus:
        raise HTTPException(400, f"Établissement inconnu : {', '.join(inconnus)}")
    return list(dict.fromkeys(hopitaux))


def _remplacer_champs(db: Session, demande: Demande, champs_in) -> None:
    for ancien in list(demande.champs_demandes):
        db.delete(ancien)
    demande.champs_demandes = []
    db.flush()
    for c in champs_in:
        champ = db.get(Champ, c.champ_id)
        if not champ or champ.lot_id != demande.lot_id:
            raise HTTPException(400, f"Champ {c.champ_id} absent du lot demandé")
        demande.champs_demandes.append(
            DemandeChamp(champ_id=champ.id, mode=c.mode, justification=c.justification)
        )
    db.flush()


# --------------------------------------------------------------------------
# Cycle de vie côté chercheur
# --------------------------------------------------------------------------
@router.post("", response_model=DemandeOut, status_code=201)
def creer(
    payload: DemandeIn,
    db: Session = Depends(get_db),
    user: Utilisateur = Depends(exiger_role(Role.CHERCHEUR)),
):
    lot = db.get(LotDonnees, payload.lot_id)
    if not lot:
        raise HTTPException(404, "Lot de données introuvable")
    demande = Demande(
        demandeur_id=user.id,
        lot_id=payload.lot_id,
        titre_projet=payload.titre_projet,
        finalite=payload.finalite,
        base_legale=payload.base_legale,
        date_debut_souhaitee=payload.date_debut_souhaitee,
        date_fin_souhaitee=payload.date_fin_souhaitee,
    )
    demande.services = _verifier_services(db, lot, payload.services)
    demande.hopitaux = _verifier_hopitaux(db, lot, payload.hopitaux)
    db.add(demande)
    db.flush()
    _remplacer_champs(db, demande, payload.champs)
    journaliser(db, user, "DEMANDE_CREEE", "demande", demande.id,
                titre=demande.titre_projet)
    db.commit()
    db.refresh(demande)
    return demande


@router.get("", response_model=list[DemandeOut])
def lister(
    statut: StatutDemande | None = None,
    db: Session = Depends(get_db),
    user: Utilisateur = Depends(LECTEURS),
):
    requete = select(Demande).order_by(Demande.cree_le.desc())
    if user.role == Role.CHERCHEUR:
        requete = requete.where(Demande.demandeur_id == user.id)
    else:
        requete = requete.where(Demande.statut != StatutDemande.BROUILLON)
    if statut:
        requete = requete.where(Demande.statut == statut)
    return db.scalars(requete).all()


@router.get("/{demande_id}", response_model=DemandeOut)
def detail(
    demande_id: int,
    db: Session = Depends(get_db),
    user: Utilisateur = Depends(LECTEURS),
):
    return _recuperer(db, demande_id, user)


@router.patch("/{demande_id}", response_model=DemandeOut)
def modifier(
    demande_id: int,
    payload: DemandeUpdate,
    db: Session = Depends(get_db),
    user: Utilisateur = Depends(exiger_role(Role.CHERCHEUR)),
):
    demande = _recuperer_proprietaire(db, demande_id, user)
    if demande.statut != StatutDemande.BROUILLON:
        raise HTTPException(409, "Seule une demande au statut BROUILLON est modifiable")
    donnees = payload.model_dump(exclude_unset=True)
    champs = donnees.pop("champs", None)
    services = donnees.pop("services", None)
    hopitaux = donnees.pop("hopitaux", None)
    if services is not None:
        demande.services = _verifier_services(db, demande.lot, services)
    if hopitaux is not None:
        demande.hopitaux = _verifier_hopitaux(db, demande.lot, hopitaux)
    for cle, valeur in donnees.items():
        setattr(demande, cle, valeur)
    if champs is not None:
        _remplacer_champs(db, demande, payload.champs)
    journaliser(db, user, "DEMANDE_MODIFIEE", "demande", demande.id,
                champs_modifies=list(donnees))
    db.commit()
    db.refresh(demande)
    return demande


@router.get("/{demande_id}/controle-rgpd", response_model=RapportConformite)
def controle_rgpd(
    demande_id: int,
    db: Session = Depends(get_db),
    user: Utilisateur = Depends(LECTEURS),
):
    demande = _recuperer(db, demande_id, user)
    return conformite.rapport(demande)


@router.post("/{demande_id}/soumettre", response_model=DemandeOut)
def soumettre(
    demande_id: int,
    db: Session = Depends(get_db),
    user: Utilisateur = Depends(exiger_role(Role.CHERCHEUR)),
):
    demande = _recuperer_proprietaire(db, demande_id, user)
    if demande.statut != StatutDemande.BROUILLON:
        raise HTTPException(409, "Demande déjà soumise")

    rapport = conformite.rapport(demande)
    if not rapport["conforme"]:
        journaliser(db, user, "SOUMISSION_REFUSEE_AUTO", "demande", demande.id,
                    alertes=[a["code"] for a in rapport["alertes"]])
        db.commit()
        raise HTTPException(422, {
            "message": "La demande viole des règles bloquantes.",
            "rapport": rapport,
        })

    demande.statut = StatutDemande.SOUMISE
    demande.soumise_le = maintenant()
    journaliser(db, user, "DEMANDE_SOUMISE", "demande", demande.id)
    db.commit()
    db.refresh(demande)
    return demande


# --------------------------------------------------------------------------
# Instruction côté DPO
# --------------------------------------------------------------------------
@router.post("/{demande_id}/instruire", response_model=DemandeOut)
def instruire(
    demande_id: int,
    db: Session = Depends(get_db),
    user: Utilisateur = Depends(exiger_role(Role.DPO)),
):
    demande = _recuperer(db, demande_id, user)
    if demande.statut != StatutDemande.SOUMISE:
        raise HTTPException(409, "Seule une demande SOUMISE peut être mise en instruction")
    demande.statut = StatutDemande.EN_INSTRUCTION
    journaliser(db, user, "INSTRUCTION_OUVERTE", "demande", demande.id)
    db.commit()
    db.refresh(demande)
    return demande


@router.post("/{demande_id}/valider", response_model=DecisionOut)
def valider(
    demande_id: int,
    payload: DecisionIn,
    db: Session = Depends(get_db),
    user: Utilisateur = Depends(exiger_role(Role.DPO)),
):
    demande = _recuperer(db, demande_id, user)
    if demande.statut not in (StatutDemande.SOUMISE, StatutDemande.EN_INSTRUCTION):
        raise HTTPException(409, "La demande n'est pas en cours d'instruction")

    # Second contrôle : la demande a pu être créée avant un durcissement des règles
    rapport = conformite.rapport(demande)
    if not rapport["conforme"]:
        raise HTTPException(422, {
            "message": "Validation impossible : règles bloquantes non levées.",
            "rapport": rapport,
        })

    date_fin = payload.date_fin_acces or demande.date_fin_souhaitee
    if date_fin > demande.date_fin_souhaitee:
        raise HTTPException(
            400, "La date de fin accordée ne peut pas dépasser celle demandée"
        )

    decision = Decision(
        demande_id=demande.id,
        dpo_id=user.id,
        sens=(SensDecision.VALIDEE_SOUS_CONDITION if payload.sous_condition
              else SensDecision.VALIDEE),
        motif=payload.motif,
        conditions=payload.conditions,
        date_fin_acces=date_fin,
    )
    autorisation = Autorisation(
        demande_id=demande.id,
        date_debut=max(demande.date_debut_souhaitee, date.today()),
        date_fin=date_fin,
        statut=StatutAutorisation.ACTIVE,
    )
    demande.statut = StatutDemande.VALIDEE
    db.add_all([decision, autorisation])
    db.flush()
    notifications.creer(
        db, demande.demandeur_id, TypeNotification.DECISION_VALIDEE,
        f"Accès accordé — {demande.titre_projet}",
        f"Votre demande n° {demande.id} est validée. L'accès prend fin le "
        f"{date_fin.strftime('%d/%m/%Y')}."
        + (f" Conditions : {payload.conditions}" if payload.conditions else ""),
        demande_id=demande.id, autorisation_id=autorisation.id,
    )

    pdf = attestation.generer(
        reference=demande.reference, titre_projet=demande.titre_projet,
        finalite=demande.finalite, demandeur_nom=demande.demandeur.nom_complet,
        demandeur_service=demande.demandeur.service, dpo_nom=user.nom_complet,
        motif=payload.motif or "Demande conforme aux règles de gouvernance.",
        conditions=payload.conditions or "", date_debut=autorisation.date_debut,
        date_fin=autorisation.date_fin, date_purge=autorisation.date_purge_prevue,
        colonnes=[dc.champ.libelle for dc in demande.champs_demandes],
        services=demande.services, prise_le=decision.prise_le,
    )
    mailer.demande_acceptee(
        db, demande.demandeur.email, demande.demandeur.nom_complet, demande.reference,
        demande.titre_projet, date_fin.strftime("%d/%m/%Y"),
        attestation=(f"attestation-{demande.reference}.pdf", pdf),
    )

    journaliser(db, user, "DEMANDE_VALIDEE", "demande", demande.id,
                date_fin_acces=date_fin, sous_condition=payload.sous_condition)
    db.commit()
    db.refresh(decision)
    return decision


@router.post("/{demande_id}/refuser", response_model=DecisionOut)
def refuser(
    demande_id: int,
    payload: DecisionIn,
    db: Session = Depends(get_db),
    user: Utilisateur = Depends(exiger_role(Role.DPO)),
):
    demande = _recuperer(db, demande_id, user)
    if demande.statut not in (StatutDemande.SOUMISE, StatutDemande.EN_INSTRUCTION):
        raise HTTPException(409, "La demande n'est pas en cours d'instruction")

    decision = Decision(
        demande_id=demande.id,
        dpo_id=user.id,
        sens=SensDecision.REFUSEE,
        motif=payload.motif,
    )
    demande.statut = StatutDemande.REFUSEE
    db.add(decision)
    db.flush()
    notifications.creer(
        db, demande.demandeur_id, TypeNotification.DECISION_REFUSEE,
        f"Demande refusée — {demande.titre_projet}",
        f"Motif communiqué par le délégué à la protection des données : {payload.motif}",
        demande_id=demande.id,
    )
    mailer.demande_refusee(
        db, demande.demandeur.email, demande.demandeur.nom_complet, demande.reference,
        demande.titre_projet, payload.motif,
    )
    journaliser(db, user, "DEMANDE_REFUSEE", "demande", demande.id, motif=payload.motif)
    db.commit()
    db.refresh(decision)
    return decision
