"""Peuple la base : comptes, catalogue et jeux de données.

    python -m app.seed            # complète une base existante
    python -m app.seed --reset    # repart d'une base vide

Quatre jeux de données :

- **Séjours hospitaliers** : synthétiques, sur l'ensemble des services d'un CHU
  (voir donnees_services.py). Aucune donnée réelle, et **aucune identité** : ni
  nom, ni prénom, ni numéro de sécurité sociale. L'identité reste dans le
  dossier de soins, hors du périmètre du portail (RGPD art. 5.1.c). Chaque
  séjour est rattaché à un établissement du territoire (voir donnees_hopitaux.py).
- **Médicaments et maladies traitées** : référentiel public (data/cis-pathologie.csv).
- **Causes de décès en France** : statistiques publiques déjà agrégées
  (data/ensemble_tableaux_2024.csv).
- **Indicateurs territoriaux par établissement** : taux d'hospitalisation, taux
  de mortalité et hospitalisations COVID-19 par hôpital et par année, à la
  manière d'un observatoire régional de santé. Statistiques déjà agrégées :
  aucun patient concerné.

Le tirage des séjours est amorcé avec une graine fixe : deux exécutions
produisent la même base, ce qui rend les démonstrations reproductibles.
"""
import csv
import random
import sys
from datetime import date
from pathlib import Path

from sqlalchemy import select

from app import donnees_hopitaux, donnees_services
from app.config import DATABASE_URL
from app.database import Base, SessionLocal, engine
from app.models import (
    CategorieChamp, Champ, DecesStat, Hopital, IndicateurHopital, LotDonnees,
    MedicamentPathologie, Patient, Role, Sejour, Utilisateur,
)
from app.security import hacher_mot_de_passe

GRAINE = 20260908
NB_SEJOURS = 5000
ANNEES_INDICATEURS = range(2020, 2025)
DOSSIER_DONNEES = Path(__file__).resolve().parent.parent / "data"

# (email, mot de passe, nom, service, rôle)
UTILISATEURS = [
    ("dpo@chu-sophia.fr", "DPO2026!", "Nadia Belkacem", "Direction juridique", Role.DPO),
    ("chercheur@chu-sophia.fr", "Chercheur2026!", "Paul Ferrand", "Cardiologie", Role.CHERCHEUR),
    ("chercheur2@chu-sophia.fr", "Chercheur2026!", "Lina Ravel", "Santé publique", Role.CHERCHEUR),
    ("admin@chu-sophia.fr", "Admin2026!", "Service informatique", "DSI", Role.ADMIN),
]

ID, QUASI, SANTE = (CategorieChamp.IDENTIFIANT_DIRECT, CategorieChamp.QUASI_IDENTIFIANT,
                    CategorieChamp.DONNEE_SANTE)
ADMIN, PUBLIC = CategorieChamp.ADMINISTRATIF, CategorieChamp.DONNEE_PUBLIQUE

CHAMPS_INDICATEURS = [
    ("etablissement", "Établissement", ADMIN, "hopital.nom", "Établissement"),
    ("ville", "Ville", ADMIN, "hopital.ville", "Établissement"),
    ("region", "Région", ADMIN, "hopital.region", "Établissement"),
    ("departement", "Département", ADMIN, "hopital.departement", "Établissement"),
    ("annee", "Année", PUBLIC, "indicateur.annee", "Période"),
    ("taux_hospitalisation", "Taux d'hospitalisation (pour 100 000 hab.)", PUBLIC,
     "indicateur.taux_hospitalisation", "Chiffres"),
    ("taux_mortalite", "Taux de mortalité (pour 100 000 hab.)", PUBLIC,
     "indicateur.taux_mortalite", "Chiffres"),
    ("hospitalisations_covid", "Hospitalisations liées au COVID-19", PUBLIC,
     "indicateur.hospitalisations_covid", "Chiffres"),
]

# (code, libellé, catégorie, source, thème affiché à l'écran)
CHAMPS_SEJOURS = [
    ("patient", "Identifiant du patient", ID, "patient.id", "Identité du patient"),
    ("age", "Âge à l'admission", QUASI, "calcul.age", "Profil du patient"),
    ("date_naissance", "Date de naissance", QUASI, "patient.date_naissance", "Profil du patient"),
    ("sexe", "Sexe", QUASI, "patient.sexe", "Profil du patient"),
    ("departement", "Département", QUASI, "calcul.departement", "Profil du patient"),
    ("commune", "Commune", QUASI, "patient.commune", "Profil du patient"),
    ("diagnostic", "Diagnostic principal (code et nom)", SANTE, "sejour.diagnostic", "Maladie"),
    ("resultat_analyse", "Résultat d'examen (biologie, imagerie...)", SANTE,
     "sejour.resultat_analyse", "Maladie"),
    ("traitements", "Traitement principal", SANTE, "sejour.traitements", "Traitement"),
    ("service", "Service", ADMIN, "sejour.service", "Séjour"),
    ("date_entree", "Date d'entrée", QUASI, "sejour.date_entree", "Séjour"),
    ("duree_sejour", "Durée du séjour (jours)", ADMIN, "sejour.duree_sejour", "Séjour"),
    ("mode_sortie", "Mode de sortie", ADMIN, "sejour.mode_sortie", "Séjour"),
    ("motif_admission", "Motif d'admission", SANTE, "sejour.motif_admission", "Urgences uniquement"),
    ("gravite_ccmu", "Gravité CCMU (de 1 à 5)", SANTE, "sejour.gravite_ccmu", "Urgences uniquement"),
    ("attente_minutes", "Temps d'attente (minutes)", ADMIN, "sejour.attente_minutes", "Urgences uniquement"),
]

CHAMPS_MEDICAMENTS = [
    ("code_cis", "Code du médicament (CIS)", PUBLIC, "medicament.code_cis", "Médicament"),
    ("pathologie", "Maladie traitée", PUBLIC, "medicament.pathologie", "Maladie"),
]

CHAMPS_DECES = [
    ("annee", "Année du décès", PUBLIC, "deces.annee", "Période"),
    ("cause", "Cause de décès", PUBLIC, "deces.cause", "Cause"),
    ("sexe", "Sexe", PUBLIC, "deces.sexe", "Population"),
    ("classe_age", "Classe d'âge", PUBLIC, "deces.classe_age", "Population"),
    ("effectifs", "Nombre de décès", PUBLIC, "deces.effectifs", "Chiffres"),
    ("taux_standardise", "Taux standardisé (pour 100 000 habitants)", PUBLIC, "deces.taux_standardise", "Chiffres"),
    ("age_median", "Âge médian au décès (2024)", PUBLIC, "deces.age_median", "Chiffres"),
    ("part_cause", "Part de la cause (parmi le sexe et l'âge)", PUBLIC, "deces.part_cause", "Chiffres"),
]

LOTS = [
    {
        "code": "SEJOURS",
        "libelle": "Séjours hospitaliers",
        "description": "Historique des séjours de tous les services : maladie, traitement, "
                       "durée, mode de sortie. Aucun nom de patient dans cette base.",
        "responsable": "Direction de l'information médicale",
        "source_donnees": "SEJOUR",
        "champs": CHAMPS_SEJOURS,
    },
    {
        "code": "MEDICAMENTS",
        "libelle": "Médicaments et maladies traitées",
        "description": "Pour chaque médicament (code CIS), les maladies pour lesquelles il est "
                       "utilisé. Donnée de référence : aucun patient concerné.",
        "responsable": "Pharmacie hospitalière",
        "source_donnees": "MEDICAMENT",
        "champs": CHAMPS_MEDICAMENTS,
    },
    {
        "code": "DECES_FRANCE",
        "libelle": "Causes de décès en France",
        "description": "Nombre de décès par cause, sexe et classe d'âge, de 2015 à 2024. "
                       "Statistiques nationales déjà agrégées : aucun patient concerné.",
        "responsable": "Direction de l'information médicale",
        "source_donnees": "DECES",
        "champs": CHAMPS_DECES,
    },
    {
        "code": "INDICATEURS",
        "libelle": "Indicateurs de santé par territoire",
        "description": "Taux d'hospitalisation, taux de mortalité et hospitalisations "
                       "COVID-19 par établissement et par année (2020-2024). "
                       "Statistiques déjà agrégées : aucun patient concerné.",
        "responsable": "Direction de l'information médicale",
        "source_donnees": "INDICATEUR",
        "champs": CHAMPS_INDICATEURS,
    },
]


# ------------------------------------------------------------------ lecture des fichiers publics
def _decimal(texte: str) -> float | None:
    """« 892,5 » -> 892.5 ; une case vide reste vide."""
    texte = (texte or "").strip().replace("\u202f", "").replace(" ", "").replace(",", ".")
    return float(texte) if texte else None


def lire_medicaments(chemin: Path) -> list[dict]:
    with open(chemin, encoding="utf-8-sig", newline="") as f:
        return [{"code_cis": ligne["Code_CIS"].strip(), "pathologie": ligne["Pathologie"].strip()}
                for ligne in csv.DictReader(f, delimiter="\t")
                if ligne["Code_CIS"].strip() and ligne["Pathologie"].strip()]


def lire_deces(chemin: Path) -> list[dict]:
    lignes = []
    with open(chemin, encoding="utf-8-sig", newline="") as f:
        for ligne in csv.DictReader(f):
            effectifs = _decimal(ligne["effectifs"])
            lignes.append({
                "annee": int(ligne["annee_dc"]),
                "cause": ligne["cause"].strip(),
                "sexe": ligne["sexe"].strip(),
                "classe_age": ligne["classe_age"].strip(),
                "effectifs": None if effectifs is None else int(effectifs),
                "taux_standardise": _decimal(ligne["tx_stand"]),
                "age_median": _decimal(ligne["mediane"]),
                "part_cause": _decimal(ligne["part_cause_parmi_sexe_age"]),
            })
    return lignes


# ------------------------------------------------------------------ peuplement
def peupler() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        for email, mdp, nom, service, role in UTILISATEURS:
            if db.scalar(select(Utilisateur).where(Utilisateur.email == email)):
                continue
            db.add(Utilisateur(
                email=email, nom_complet=nom, service=service, role=role,
                mot_de_passe_hash=hacher_mot_de_passe(mdp),
            ))

        for donnees in LOTS:
            if db.scalar(select(LotDonnees).where(LotDonnees.code == donnees["code"])):
                continue
            lot = LotDonnees(
                code=donnees["code"], libelle=donnees["libelle"],
                description=donnees["description"], responsable=donnees["responsable"],
                source_donnees=donnees["source_donnees"],
            )
            lot.champs = [
                Champ(code=c, libelle=lib, categorie=cat, source=src, groupe=groupe)
                for c, lib, cat, src, groupe in donnees["champs"]
            ]
            db.add(lot)

        alea = random.Random(GRAINE)

        if not db.scalar(select(Hopital.id).limit(1)):
            db.add_all([
                Hopital(code=code, nom=nom, ville=ville, region=region,
                        departement=dept, latitude=lat, longitude=lon,
                        population_bassin=pop)
                for code, nom, ville, region, dept, lat, lon, pop in donnees_hopitaux.HOPITAUX
            ])
            lignes_indicateurs = [
                ligne
                for hopital in donnees_hopitaux.HOPITAUX
                for ligne in donnees_hopitaux.generer_indicateurs(alea, hopital, ANNEES_INDICATEURS)
            ]
            db.add_all([
                IndicateurHopital(hopital_code=l["code_hopital"], annee=l["annee"],
                                  taux_hospitalisation=l["taux_hospitalisation"],
                                  taux_mortalite=l["taux_mortalite"],
                                  hospitalisations_covid=l["hospitalisations_covid"])
                for l in lignes_indicateurs
            ])
            print(f"{len(donnees_hopitaux.HOPITAUX)} établissements et "
                  f"{len(lignes_indicateurs)} indicateurs annuels créés.")

        if not db.scalar(select(Patient.id).limit(1)):
            patients, sejours = donnees_services.generer(
                random.Random(GRAINE), NB_SEJOURS, date.today())
            objets = [Patient(date_naissance=p["date_naissance"], sexe=p["sexe"],
                              code_postal=p["code_postal"], commune=p["commune"])
                      for p in patients]
            db.add_all(objets)
            db.add_all([
                Sejour(patient=objets[j["patient_indice"]],
                       hopital_code=donnees_hopitaux.assigner_hopital(
                           alea, donnees_hopitaux.HOPITAUX, j["service"]),
                       **{k: v for k, v in j.items() if k != "patient_indice"})
                for j in sejours
            ])
            print(f"{len(objets)} patients et {len(sejours)} séjours créés "
                  f"({len(donnees_services.NOMS_SERVICES)} services, "
                  f"{len(donnees_hopitaux.HOPITAUX)} établissements).")

        if not db.scalar(select(MedicamentPathologie.id).limit(1)):
            lignes = lire_medicaments(DOSSIER_DONNEES / "cis-pathologie.csv")
            db.execute(MedicamentPathologie.__table__.insert(), lignes)
            print(f"{len(lignes)} associations médicament-maladie chargées.")

        if not db.scalar(select(DecesStat.id).limit(1)):
            lignes = lire_deces(DOSSIER_DONNEES / "ensemble_tableaux_2024.csv")
            db.execute(DecesStat.__table__.insert(), lignes)
            print(f"{len(lignes)} lignes de statistiques de décès chargées.")

        db.commit()
        print("Base peuplée. Comptes : dpo@chu-sophia.fr / DPO2026!, "
              "chercheur@chu-sophia.fr / Chercheur2026!, admin@chu-sophia.fr / Admin2026!")
    finally:
        db.close()


def reinitialiser() -> None:
    """Supprime le fichier SQLite puis repeuple (uniquement pour SQLite)."""
    if DATABASE_URL.startswith("sqlite:///"):
        engine.dispose()
        Path(DATABASE_URL.removeprefix("sqlite:///")).unlink(missing_ok=True)
    peupler()


if __name__ == "__main__":
    if "--reset" in sys.argv:
        reinitialiser()
    else:
        peupler()
