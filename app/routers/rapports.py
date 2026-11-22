"""Indicateurs de pilotage de la gouvernance des accès (MED-19, MED-20)."""
import csv
import io
from collections import Counter
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import conformite
from app.config import DELAI_PREAVIS_JOURS
from app.database import get_db
from app.dependencies import exiger_role
from app.models import (
    Autorisation, Champ, Decision, Demande, DemandeChamp, JournalAudit, Role,
    SensDecision, StatutAutorisation, StatutDemande, Utilisateur,
)
from app.schemas import EcheanceOut, LigneIndicateur, SyntheseOut, TableauDeBordOut

router = APIRouter(prefix="/rapports", tags=["Pilotage"])

PILOTES = exiger_role(Role.DPO, Role.ADMIN)


def _compter(db: Session, colonne, filtre=None) -> list[LigneIndicateur]:
    requete = select(colonne, func.count()).group_by(colonne)
    if filtre is not None:
        requete = requete.where(filtre)
    return [
        LigneIndicateur(libelle=getattr(cle, "value", str(cle)), valeur=n)
        for cle, n in db.execute(requete).all()
    ]


# --------------------------------------------------------------------------
# MED-20 — Tableau de bord
# --------------------------------------------------------------------------
@router.get("/tableau-de-bord", response_model=TableauDeBordOut,
            dependencies=[Depends(PILOTES)])
def tableau_de_bord(db: Session = Depends(get_db)):
    aujourdhui = date.today()
    limite = aujourdhui + timedelta(days=DELAI_PREAVIS_JOURS)

    a_instruire = db.scalar(select(func.count(Demande.id)).where(
        Demande.statut.in_([StatutDemande.SOUMISE, StatutDemande.EN_INSTRUCTION])))

    acces_actifs = db.scalar(select(func.count(Autorisation.id)).where(
        Autorisation.statut == StatutAutorisation.ACTIVE))

    # Accès clos mais dont la suppression n'est pas encore attestée
    dette = db.scalar(select(func.count(Autorisation.id)).where(
        Autorisation.statut.in_(
            [StatutAutorisation.EXPIREE, StatutAutorisation.REVOQUEE])))

    bloquees = db.scalar(select(func.count(JournalAudit.id)).where(
        JournalAudit.action == "SOUMISSION_REFUSEE_AUTO"))

    proches = db.scalars(
        select(Autorisation).where(
            Autorisation.statut == StatutAutorisation.ACTIVE,
            Autorisation.date_fin <= limite,
            Autorisation.date_fin >= aujourdhui,
        ).order_by(Autorisation.date_fin)
    ).all()

    return TableauDeBordOut(
        a_instruire=a_instruire or 0,
        acces_actifs=acces_actifs or 0,
        echeances_proches=len(proches),
        dette_de_purge=dette or 0,
        soumissions_bloquees=bloquees or 0,
        demandes_par_statut=_compter(db, Demande.statut),
        acces_par_statut=_compter(db, Autorisation.statut),
        echeances=[
            EcheanceOut(
                autorisation=a,
                titre_projet=a.demande.titre_projet,
                demandeur=a.demande.demandeur.nom_complet,
                jours_restants=(a.date_fin - aujourdhui).days,
            ) for a in proches
        ],
    )


# --------------------------------------------------------------------------
# MED-19 — Synthèse sur une période
# --------------------------------------------------------------------------
def _synthese(db: Session, debut: date, fin: date) -> SyntheseOut:
    borne_debut = datetime.combine(debut, datetime.min.time())
    borne_fin = datetime.combine(fin, datetime.max.time())
    dans_periode = (Demande.cree_le >= borne_debut) & (Demande.cree_le <= borne_fin)

    demandes = db.scalars(select(Demande).where(dans_periode)).all()
    ids = [d.id for d in demandes]

    decisions = db.scalars(
        select(Decision).where(Decision.demande_id.in_(ids))
    ).all() if ids else []
    validees = [d for d in decisions if d.sens != SensDecision.REFUSEE]
    refusees = [d for d in decisions if d.sens == SensDecision.REFUSEE]

    # Délai d'instruction : de la soumission à la décision
    delais = []
    for decision in decisions:
        soumise = decision.demande.soumise_le
        if soumise:
            prise = decision.prise_le
            if soumise.tzinfo and not prise.tzinfo:
                prise = prise.replace(tzinfo=timezone.utc)
            if prise.tzinfo and not soumise.tzinfo:
                soumise = soumise.replace(tzinfo=timezone.utc)
            delais.append((prise - soumise).total_seconds() / 86400)

    autorisations = db.scalars(
        select(Autorisation).where(Autorisation.demande_id.in_(ids))
    ).all() if ids else []
    durees = [(a.date_fin - a.date_debut).days for a in autorisations]

    # Répartition des colonnes demandées
    categories, modes = Counter(), Counter()
    for demande in demandes:
        for liaison in demande.champs_demandes:
            categories[liaison.champ.categorie.value] += 1
            modes[liaison.mode.value] += 1

    # Alertes les plus fréquentes : on rejoue le moteur sur la période
    alertes = Counter()
    for demande in demandes:
        for alerte in conformite.analyser(demande):
            alertes[alerte.code] += 1

    bloquees = db.scalar(select(func.count(JournalAudit.id)).where(
        JournalAudit.action == "SOUMISSION_REFUSEE_AUTO",
        JournalAudit.horodatage >= borne_debut,
        JournalAudit.horodatage <= borne_fin,
    )) or 0

    statuts = Counter(d.statut.value for d in demandes)

    return SyntheseOut(
        periode_debut=debut,
        periode_fin=fin,
        demandes_deposees=len(demandes),
        demandes_soumises=sum(1 for d in demandes if d.soumise_le),
        demandes_validees=len(validees),
        demandes_refusees=len(refusees),
        taux_de_refus=round(len(refusees) / len(decisions) * 100, 1) if decisions else 0.0,
        soumissions_bloquees=bloquees,
        delai_moyen_instruction_jours=round(sum(delais) / len(delais), 2) if delais else None,
        duree_moyenne_acces_jours=round(sum(durees) / len(durees), 1) if durees else None,
        acces_purges=sum(1 for a in autorisations
                         if a.statut == StatutAutorisation.PURGEE),
        demandes_par_statut=[LigneIndicateur(libelle=k, valeur=v)
                             for k, v in statuts.most_common()],
        colonnes_par_categorie=[LigneIndicateur(libelle=k, valeur=v)
                                for k, v in categories.most_common()],
        colonnes_par_mode=[LigneIndicateur(libelle=k, valeur=v)
                           for k, v in modes.most_common()],
        alertes_les_plus_frequentes=[LigneIndicateur(libelle=k, valeur=v)
                                     for k, v in alertes.most_common(5)],
    )


@router.get("/synthese", response_model=SyntheseOut, dependencies=[Depends(PILOTES)])
def synthese(
    debut: date = Query(default=None, description="Par défaut : 90 jours en arrière"),
    fin: date = Query(default=None, description="Par défaut : aujourd'hui"),
    db: Session = Depends(get_db),
):
    fin = fin or date.today()
    debut = debut or (fin - timedelta(days=90))
    return _synthese(db, debut, fin)


@router.get("/synthese/export", dependencies=[Depends(PILOTES)])
def exporter_synthese(
    debut: date = None, fin: date = None, db: Session = Depends(get_db),
):
    """Synthèse au format CSV, à joindre au registre des traitements."""
    fin = fin or date.today()
    debut = debut or (fin - timedelta(days=90))
    s = _synthese(db, debut, fin)

    tampon = io.StringIO()
    ecrivain = csv.writer(tampon, delimiter=";")
    ecrivain.writerow(["Indicateur", "Valeur"])
    ecrivain.writerow(["Période", f"{debut} au {fin}"])
    for libelle, valeur in [
        ("Demandes déposées", s.demandes_deposees),
        ("Demandes soumises", s.demandes_soumises),
        ("Demandes validées", s.demandes_validees),
        ("Demandes refusées", s.demandes_refusees),
        ("Taux de refus (%)", s.taux_de_refus),
        ("Soumissions bloquées par le contrôle", s.soumissions_bloquees),
        ("Délai moyen d'instruction (jours)", s.delai_moyen_instruction_jours or ""),
        ("Durée moyenne d'accès (jours)", s.duree_moyenne_acces_jours or ""),
        ("Accès purgés", s.acces_purges),
    ]:
        ecrivain.writerow([libelle, valeur])

    for titre, lignes in [
        ("Demandes par statut", s.demandes_par_statut),
        ("Colonnes par catégorie", s.colonnes_par_categorie),
        ("Colonnes par mode d'accès", s.colonnes_par_mode),
        ("Alertes les plus fréquentes", s.alertes_les_plus_frequentes),
    ]:
        ecrivain.writerow([])
        ecrivain.writerow([titre, "Nombre"])
        for ligne in lignes:
            ecrivain.writerow([ligne.libelle, ligne.valeur])

    return Response(
        content="\ufeff" + tampon.getvalue(),  # BOM : Excel ouvre l'UTF-8 correctement
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition":
                 f'attachment; filename="synthese-acces-{debut}-{fin}.csv"'},
    )
