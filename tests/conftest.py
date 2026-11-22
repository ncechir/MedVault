import os

os.environ["PLANIFICATEUR"] = "0"  # pas de thread de fond pendant les tests
os.environ["SEED_AUTO"] = "0"      # pas de jeu de démonstration dans les tests

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import (
    CategorieChamp, Champ, LotDonnees, Patient, Role, Sejour, Utilisateur,
)
from app.security import hacher_mot_de_passe

MDP = "Test2026!"


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def donnees(db_session):
    """Deux chercheurs, un DPO, un lot avec des champs de chaque catégorie."""
    utilisateurs = {
        "chercheur": Utilisateur(
            email="p.ferrand@chu.fr", nom_complet="Paul Ferrand", role=Role.CHERCHEUR,
            mot_de_passe_hash=hacher_mot_de_passe(MDP)),
        "chercheur2": Utilisateur(
            email="l.ravel@chu.fr", nom_complet="Lina Ravel", role=Role.CHERCHEUR,
            mot_de_passe_hash=hacher_mot_de_passe(MDP)),
        "dpo": Utilisateur(
            email="dpo@chu.fr", nom_complet="Nadia Belkacem", role=Role.DPO,
            mot_de_passe_hash=hacher_mot_de_passe(MDP)),
        "admin": Utilisateur(
            email="admin@chu.fr", nom_complet="DSI", role=Role.ADMIN,
            mot_de_passe_hash=hacher_mot_de_passe(MDP)),
    }
    lot = LotDonnees(code="SEJOURS", libelle="Séjours cardiologie",
                     service_source="Cardiologie")
    lot.champs = [
        Champ(code="nom", libelle="Nom", categorie=CategorieChamp.IDENTIFIANT_DIRECT,
              source="patient.nom"),
        Champ(code="prenom", libelle="Prénom", categorie=CategorieChamp.IDENTIFIANT_DIRECT,
              source="patient.prenom"),
        Champ(code="ddn", libelle="Date de naissance", categorie=CategorieChamp.QUASI_IDENTIFIANT,
              source="patient.date_naissance"),
        Champ(code="cp", libelle="Code postal", categorie=CategorieChamp.QUASI_IDENTIFIANT,
              source="patient.code_postal"),
        Champ(code="sexe", libelle="Sexe", categorie=CategorieChamp.QUASI_IDENTIFIANT,
              source="patient.sexe"),
        Champ(code="diag", libelle="Diagnostic", categorie=CategorieChamp.DONNEE_SANTE,
              source="sejour.diagnostic_cim10"),
        Champ(code="duree", libelle="Durée de séjour", categorie=CategorieChamp.ADMINISTRATIF,
              source="sejour.duree_sejour"),
    ]

    # Deux patients, trois séjours : de quoi vérifier les transformations
    marie = Patient(ipp="IPP000001", nom="Durand", prenom="Marie",
                    num_secu="2850612345678", date_naissance=date(1985, 6, 12),
                    sexe="F", code_postal="06130", commune="Grasse")
    hugo = Patient(ipp="IPP000002", nom="Lefebvre", prenom="Hugo",
                   num_secu="1520398765432", date_naissance=date(1952, 3, 4),
                   sexe="M", code_postal="06000", commune="Nice")
    sejours = [
        Sejour(patient=marie, service="Cardiologie", date_entree=date(2025, 4, 2),
               duree_sejour=5, diagnostic_cim10="I48", traitements="Anticoagulant",
               mode_sortie="Domicile"),
        Sejour(patient=marie, service="Cardiologie", date_entree=date(2025, 9, 18),
               duree_sejour=2, diagnostic_cim10="I10", traitements="Bêtabloquant",
               mode_sortie="Domicile"),
        Sejour(patient=hugo, service="Cardiologie", date_entree=date(2025, 7, 9),
               duree_sejour=12, diagnostic_cim10="I21", traitements="Angioplastie",
               mode_sortie="Transfert SSR"),
    ]

    db_session.add_all([*utilisateurs.values(), lot, marie, hugo, *sejours])
    db_session.commit()
    for u in utilisateurs.values():
        db_session.refresh(u)
    db_session.refresh(lot)
    return {
        "users": utilisateurs,
        "lot": lot,
        "champs": {c.code: c.id for c in lot.champs},
    }


@pytest.fixture()
def entetes(client, donnees):
    """Fabrique d'en-têtes d'authentification : entetes('dpo')."""
    def _pour(cle: str) -> dict:
        email = donnees["users"][cle].email
        r = client.post("/auth/login", data={"username": email, "password": MDP})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['access_token']}"}
    return _pour


@pytest.fixture()
def demande_valide(donnees):
    """Corps de demande conforme : identités pseudonymisées, durée raisonnable."""
    champs = donnees["champs"]
    return {
        "lot_id": donnees["lot"].id,
        "titre_projet": "Analyse des réhospitalisations à 30 jours",
        "finalite": (
            "Mesurer le taux de réhospitalisation à 30 jours en cardiologie afin "
            "d'identifier les leviers d'amélioration du parcours de soin."
        ),
        "date_debut_souhaitee": str(date.today()),
        "date_fin_souhaitee": str(date.today() + timedelta(days=180)),
        "champs": [
            {"champ_id": champs["nom"], "mode": "PSEUDONYMISE"},
            {"champ_id": champs["diag"], "mode": "BRUT",
             "justification": "Nécessaire pour stratifier par pathologie."},
            {"champ_id": champs["duree"], "mode": "BRUT"},
        ],
    }
