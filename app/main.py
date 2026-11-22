import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, select, text

from app import taches
from app.config import PLANIFICATEUR_ACTIF, PLANIFICATEUR_HEURE, SEED_AUTO
from app.database import Base, SessionLocal, engine
from app.models import Utilisateur
from app.routers import (
    admin_demandes, auth, autorisations, demandes, extractions, hopitaux, import_donnees, journal,
    lots, mails, notifications, parametres, politiques, rapports, support, utilisateurs,
)

logger = logging.getLogger("medvault")


def executer_taches_quotidiennes() -> None:
    """Appelée par le planificateur, hors de tout contexte HTTP (MED-16)."""
    db = SessionLocal()
    try:
        resume = taches.executer_echeances(db, acteur=None)
        logger.info(
            "Tâche quotidienne : %s préavis, %s accès clos, %s purges.",
            resume["preavis_envoyes"], len(resume["acces_clotures"]),
            resume["donnees_purgees"],
        )
    except Exception:
        logger.exception("Échec de la tâche quotidienne d'échéances")
    finally:
        db.close()


def _verifier_schema() -> None:
    """Message clair si la base date d'une version antérieure du modèle.

    SQLite ne met pas ses tables à jour tout seul : sans ce contrôle, l'erreur
    apparaîtrait plus tard, sous la forme d'une colonne introuvable.
    """
    tables = inspect(engine).get_table_names()
    if "lot_donnees" in tables:
        colonnes = {c["name"] for c in inspect(engine).get_columns("lot_donnees")}
        if "source_donnees" not in colonnes:
            raise RuntimeError(
                "La base de données date d'une ancienne version. Arrêtez le "
                "serveur, puis lancez : python -m app.seed --reset"
            )


def _migrer_colonnes() -> None:
    """Ajoute les colonnes apparues après coup : chaînage du journal (V2) et
    photo de profil, pour qu'une base existante reste utilisable."""
    insp = inspect(engine)
    tables = insp.get_table_names()
    with engine.begin() as cx:
        if "journal_audit" in tables:
            existantes = {c["name"] for c in insp.get_columns("journal_audit")}
            for nom in ("empreinte_precedente", "empreinte"):
                if nom not in existantes:
                    cx.execute(text(f"ALTER TABLE journal_audit ADD COLUMN {nom} VARCHAR(64)"))
        if "utilisateur" in tables:
            existantes = {c["name"] for c in insp.get_columns("utilisateur")}
            if "photo" not in existantes:
                cx.execute(text("ALTER TABLE utilisateur ADD COLUMN photo TEXT"))


def _restreindre_hopitaux() -> None:
    """Prototype mono-établissement : ramène une base déjà peuplée à un seul
    hôpital (Alpes-Côte d'Azur). Les séjours des autres établissements sont
    rattachés au CHU Sophia ; leurs indicateurs et fiches sont supprimés."""
    from app import donnees_hopitaux
    code, nom, ville, region, dept, lat, lon, pop = donnees_hopitaux.HOPITAUX[0]
    insp = inspect(engine)
    if "hopital" not in insp.get_table_names():
        return
    with engine.begin() as cx:
        autres = cx.execute(text("SELECT COUNT(*) FROM hopital WHERE code <> :c"),
                            {"c": code}).scalar()
        existe = cx.execute(text("SELECT COUNT(*) FROM hopital WHERE code = :c"),
                            {"c": code}).scalar()
        if not autres or not existe:
            return
        cx.execute(text("UPDATE sejour SET hopital_code = :c WHERE hopital_code <> :c"), {"c": code})
        cx.execute(text("DELETE FROM indicateur_hopital WHERE hopital_code <> :c"), {"c": code})
        cx.execute(text("DELETE FROM hopital WHERE code <> :c"), {"c": code})
        cx.execute(text("UPDATE hopital SET nom = :n WHERE code = :c"), {"n": nom, "c": code})
        cx.execute(text("UPDATE demande SET hopitaux_json = '[]'"))
    logger.info("Base ramenée à un seul établissement : %s.", nom)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _verifier_schema()
    Base.metadata.create_all(bind=engine)
    _migrer_colonnes()
    _restreindre_hopitaux()

    if SEED_AUTO:
        # Base vide : on la peuple pour que le portail soit utilisable dès le
        # premier lancement, sans étape manuelle à oublier.
        with SessionLocal() as db:
            vide = db.scalar(select(Utilisateur.id).limit(1)) is None
        if vide:
            from app.seed import peupler
            peupler()
            logger.info("Base vide : jeu de démonstration créé.")

    planificateur = None
    if PLANIFICATEUR_ACTIF:
        from apscheduler.schedulers.background import BackgroundScheduler

        planificateur = BackgroundScheduler(timezone="Europe/Paris")
        planificateur.add_job(
            executer_taches_quotidiennes,
            "cron", hour=PLANIFICATEUR_HEURE, minute=0,
            id="echeances_acces", replace_existing=True,
        )
        planificateur.start()
        logger.info("Planificateur démarré : échéances chaque jour à %sh.",
                    PLANIFICATEUR_HEURE)

    yield

    if planificateur:
        planificateur.shutdown(wait=False)


app = FastAPI(
    lifespan=lifespan,
    title="Medvault — Portail d'accès aux données de santé",
    description=(
        "Dépôt, instruction et traçabilité des demandes d'accès aux données "
        "de santé pour les études internes (RGPD / AI Act)."
    ),
    version="1.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", "http://localhost:3000",
        "http://127.0.0.1:5173", "http://127.0.0.1:3000",
        "http://localhost:8000", "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(lots.router)
app.include_router(demandes.router)
app.include_router(autorisations.router)
app.include_router(extractions.router)
app.include_router(notifications.router)
app.include_router(rapports.router)
app.include_router(journal.router)
app.include_router(utilisateurs.router)
app.include_router(parametres.router)
app.include_router(hopitaux.router)
app.include_router(import_donnees.router)
app.include_router(mails.router)
app.include_router(politiques.router)
app.include_router(support.router)
app.include_router(admin_demandes.router)


@app.get("/sante", tags=["Technique"])
def sante():
    return {"statut": "ok"}


# L'interface est servie par l'API elle-même : une seule commande à lancer, une
# seule origine, donc aucun problème de CORS. Monté en dernier pour ne masquer
# aucune route de l'API.
DOSSIER_INTERFACE = Path(__file__).resolve().parent.parent / "frontend"
if DOSSIER_INTERFACE.is_dir():
    app.mount("/", StaticFiles(directory=DOSSIER_INTERFACE, html=True), name="interface")
