"""Paramètres de l'application.

Les seuils RGPD sont centralisés ici : le DPO doit pouvoir les faire évoluer
sans toucher au code métier.
"""
import os

# --- Sécurité ---
SECRET_KEY = os.getenv("SECRET_KEY", "changez-moi-en-production")
ALGORITHM = "HS256"
DUREE_TOKEN_MINUTES = 60 * 8

# --- Base de données ---
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./portail_sante.db")

# --- Règles de gouvernance ---
DUREE_ACCES_MAX_MOIS = 24        # durée de conservation maximale d'un accès
NB_CHAMPS_ALERTE = 15            # au-delà : suspicion de non-minimisation
NB_QUASI_IDENTIFIANTS_ALERTE = 3  # risque de ré-identification par croisement
LONGUEUR_FINALITE_MIN = 50       # une finalité doit être explicite
DELAI_PREAVIS_JOURS = 7          # préavis avant échéance d'un accès (MED-8)
DELAI_PURGE_JOURS = 30           # délai après échéance avant purge d'office (MED-16)

# --- Planificateur (MED-16) ---
# Mettre PLANIFICATEUR=0 pour le désactiver (tests, exécutions ponctuelles).
PLANIFICATEUR_ACTIF = os.getenv("PLANIFICATEUR", "1") != "0"
PLANIFICATEUR_HEURE = int(os.getenv("PLANIFICATEUR_HEURE", "2"))

# --- Démarrage ---
# Peuple automatiquement une base vide (comptes, catalogue, patients synthétiques).
# SEED_AUTO=0 pour désactiver (tests, base de production).
SEED_AUTO = os.getenv("SEED_AUTO", "1") != "0"

# --- Notifications par e-mail ---
# Sans serveur SMTP configuré, les e-mails ne partent pas réellement : ils sont
# consignés dans la table `email_envoye` et restent consultables depuis l'onglet
# « E-mails » (administrateur), ce qui permet de faire une démonstration
# complète sans dépendre d'un vrai compte de messagerie.
SMTP_HOTE = os.getenv("SMTP_HOTE", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_UTILISATEUR = os.getenv("SMTP_UTILISATEUR", "")
SMTP_MOT_DE_PASSE = os.getenv("SMTP_MOT_DE_PASSE", "")
SMTP_EXPEDITEUR = os.getenv("SMTP_EXPEDITEUR", "medvault@chu-sophia.fr")
SMTP_TLS = os.getenv("SMTP_TLS", "1") != "0"
NOM_ETABLISSEMENT = os.getenv("NOM_ETABLISSEMENT", "CHU Sophia")
