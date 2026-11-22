from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models import (
    CategorieChamp, ModeAcces, Role, SensDecision, StatutAutorisation, StatutDemande,
    TypeNotification,
)


class Base(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def _en_utc(valeur: datetime) -> datetime:
    """SQLite ne conserve pas le fuseau : les dates stockées sont en UTC mais
    « naïves ». Sans indication, le navigateur les lit comme des heures locales,
    d'où un décalage de 1 à 2 h en France. On les déclare donc explicitement en
    UTC : elles sortent avec un « Z », et le navigateur les convertit à l'heure
    de l'utilisateur."""
    if valeur.tzinfo is None:
        return valeur.replace(tzinfo=timezone.utc)
    return valeur.astimezone(timezone.utc)


UTCDatetime = Annotated[datetime, AfterValidator(_en_utc)]


# --- Auth ---
class Token(Base):
    access_token: str
    token_type: str = "bearer"


class UtilisateurOut(Base):
    id: int
    email: EmailStr
    nom_complet: str
    service: str
    role: Role


class InscriptionIn(Base):
    """Création de compte libre : adresse personnelle ou universitaire."""
    nom_complet: str = Field(min_length=3, max_length=180)
    email: EmailStr
    service: str = Field(default="", max_length=120)
    mot_de_passe: str = Field(min_length=10, max_length=128)
    engagement: bool = False

    @field_validator("mot_de_passe")
    @classmethod
    def _mot_de_passe_solide(cls, valeur: str) -> str:
        if not any(c.isalpha() for c in valeur) or not any(c.isdigit() for c in valeur):
            raise ValueError("Le mot de passe doit contenir au moins une lettre et un chiffre.")
        return valeur


class UtilisateurAdminOut(UtilisateurOut):
    """Vue de l'administrateur : ce qu'il faut pour gérer les comptes, rien de médical."""
    actif: bool
    cree_le: UTCDatetime
    nb_demandes: int = 0


class UtilisateurMaj(Base):
    role: Role | None = None
    actif: bool | None = None


# --- Lots et champs ---
class ChampOut(Base):
    id: int
    code: str
    libelle: str
    categorie: CategorieChamp
    groupe: str = ""
    # Ce que le demandeur reçoit par défaut, en langage courant
    protection: str = ""
    # Vrai si une version exacte peut être demandée (sur justification)
    reductible: bool = False


class LotOut(Base):
    id: int
    code: str
    libelle: str
    description: str
    responsable: str
    source_donnees: str = "SEJOUR"


class LotDetailOut(LotOut):
    champs: list[ChampOut]
    # Services parmi lesquels choisir (jeu de séjours uniquement)
    services: list[str] = []
    # Établissements parmi lesquels choisir (séjours et indicateurs)
    hopitaux: list["HopitalOut"] = []


# --- Demandes ---
class ChampDemandeIn(Base):
    champ_id: int
    mode: ModeAcces = ModeAcces.PSEUDONYMISE
    justification: str = ""


class DemandeIn(Base):
    lot_id: int
    titre_projet: str = Field(min_length=5, max_length=200)
    finalite: str = Field(min_length=1)
    base_legale: str = "Mission d'intérêt public (art. 6.1.e)"
    date_debut_souhaitee: date
    date_fin_souhaitee: date
    services: list[str] = []
    hopitaux: list[str] = []
    champs: list[ChampDemandeIn] = []


class DemandeUpdate(Base):
    titre_projet: str | None = None
    finalite: str | None = None
    base_legale: str | None = None
    date_debut_souhaitee: date | None = None
    date_fin_souhaitee: date | None = None
    services: list[str] | None = None
    hopitaux: list[str] | None = None
    champs: list[ChampDemandeIn] | None = None


class ChampDemandeOut(Base):
    champ: ChampOut
    mode: ModeAcces
    justification: str
    # Ce que le demandeur recevra, dit simplement : « Code anonyme », « Année seulement »...
    protection: str = ""


# --- Décisions (déclarées avant DemandeOut : la demande les expose) ---
class DecisionIn(Base):
    motif: str = Field(min_length=10)
    conditions: str = ""
    date_fin_acces: date | None = None
    sous_condition: bool = False


class DecisionOut(Base):
    id: int
    sens: SensDecision
    motif: str
    conditions: str
    date_fin_acces: date | None
    prise_le: UTCDatetime
    dpo: UtilisateurOut


class AutorisationOut(Base):
    id: int
    demande_id: int
    reference: str = ""
    titre_projet: str = ""
    demandeur_nom: str = ""
    date_debut: date
    date_fin: date
    statut: StatutAutorisation
    date_purge_prevue: date
    revoquee_le: UTCDatetime | None
    motif_revocation: str
    purge_effectuee_le: UTCDatetime | None
    decision: DecisionOut | None = None


class RevocationIn(Base):
    motif: str = Field(min_length=5)


class DemandeOut(Base):
    id: int
    reference: str
    titre_projet: str
    finalite: str
    base_legale: str
    statut: StatutDemande
    date_debut_souhaitee: date
    date_fin_souhaitee: date
    services: list[str] = []
    hopitaux: list[str] = []
    cree_le: UTCDatetime
    soumise_le: UTCDatetime | None
    demandeur: UtilisateurOut
    lot: LotOut
    champs_demandes: list[ChampDemandeOut]
    # MED-9 : le demandeur doit pouvoir lire le motif du refus
    decision: DecisionOut | None = None
    autorisation: AutorisationOut | None = None


# --- Extractions ---
class ColonneExtractionOut(Base):
    code: str
    libelle: str
    categorie: str
    mode: str
    groupe: str = ""
    transformation: str


class AgregatOut(Base):
    colonne: str
    valeur: str
    effectif: int


class ControleOut(Base):
    """Contrôle de confidentialité (k-anonymat) appliqué avant livraison."""
    score: int
    niveau: str                      # FAIBLE | MODERE | ELEVE
    k_cible: int
    k_min: int | None = None
    nb_lignes: int
    nb_lignes_a_risque: int
    nb_uniques: int = 0
    nb_lignes_supprimees: int = 0
    nb_agregats_supprimes: int = 0
    quasi_identifiants: list[str] = []
    politique: str = ""
    action: str = "AVERTIR"
    bloque: bool = False
    messages: list[str] = []


class ExtractionOut(Base):
    demande_id: int
    titre_projet: str
    lot: str
    produite_le: date
    nb_lignes: int
    # Nombre total de lignes auxquelles la demande donne droit (l'aperçu est tronqué)
    nb_total: int = 0
    colonnes: list[ColonneExtractionOut]
    identites_masquees: bool = True
    lignes: list[dict[str, str]]
    statistiques: list[AgregatOut]
    controle: ControleOut | None = None


# --- Notifications (MED-8) ---
class NotificationOut(Base):
    id: int
    type: TypeNotification
    titre: str
    message: str
    demande_id: int | None
    autorisation_id: int | None
    lue: bool
    cree_le: UTCDatetime


class EcheanceOut(Base):
    autorisation: AutorisationOut
    titre_projet: str
    demandeur: str
    jours_restants: int


class ResumeTacheOut(Base):
    """Compte rendu d'exécution de la tâche d'échéances (MED-16)."""
    preavis_envoyes: int
    acces_clotures: list[AutorisationOut]
    donnees_purgees: int


# --- Pilotage (MED-19, MED-20) ---
class LigneIndicateur(Base):
    libelle: str
    valeur: int


class TableauDeBordOut(Base):
    """État instantané, destiné à la page d'accueil du DPO (MED-20)."""
    a_instruire: int
    acces_actifs: int
    echeances_proches: int
    dette_de_purge: int
    soumissions_bloquees: int
    demandes_par_statut: list[LigneIndicateur]
    acces_par_statut: list[LigneIndicateur]
    echeances: list[EcheanceOut]


class SyntheseOut(Base):
    """Bilan sur une période, destiné au registre de traitement (MED-19)."""
    periode_debut: date
    periode_fin: date
    demandes_deposees: int
    demandes_soumises: int
    demandes_validees: int
    demandes_refusees: int
    taux_de_refus: float
    soumissions_bloquees: int
    delai_moyen_instruction_jours: float | None
    duree_moyenne_acces_jours: float | None
    acces_purges: int
    demandes_par_statut: list[LigneIndicateur]
    colonnes_par_categorie: list[LigneIndicateur]
    colonnes_par_mode: list[LigneIndicateur]
    alertes_les_plus_frequentes: list[LigneIndicateur]


# --- Audit ---
class AuditOut(Base):
    id: int
    horodatage: UTCDatetime
    utilisateur_email: str
    action: str
    entite: str
    entite_id: int | None
    details: str


# --- Conformité ---
class AlerteOut(Base):
    niveau: str
    code: str
    message: str
    reference: str


class RapportConformite(Base):
    demande_id: int | None
    conforme: bool
    nb_bloquants: int
    nb_avertissements: int
    # Aucune identité directe demandée en clair (règle R2)
    identites_masquees: bool = True
    nb_identifiants_masques: int = 0
    alertes: list[AlerteOut]


class ParametresOut(Base):
    delai_preavis_jours: int
    delai_purge_jours: int
    duree_acces_max_mois: int


# --- Établissements et indicateurs territoriaux ---
class IndicateurAnnuelOut(Base):
    annee: int
    taux_hospitalisation: float
    taux_mortalite: float
    hospitalisations_covid: int


class HopitalOut(Base):
    id: int
    code: str
    nom: str
    ville: str
    region: str
    departement: str
    latitude: float
    longitude: float
    population_bassin: int
    nb_sejours: int = 0
    dernier_indicateur: IndicateurAnnuelOut | None = None


class HopitalDetailOut(HopitalOut):
    historique: list[IndicateurAnnuelOut] = []


# --- Import de données par le délégué ---
class ImportLotOut(Base):
    id: int
    code: str
    libelle: str
    description: str
    categorie: str
    nb_lignes: int = 0
    importe_par: str = ""
    importe_le: UTCDatetime | None = None


# --- E-mails ---
class EmailOut(Base):
    id: int
    destinataire: str
    sujet: str
    corps: str
    type_notification: str
    piece_jointe_nom: str
    statut: str
    erreur: str
    cree_le: UTCDatetime


# --- Politiques de données (V2) ---
class PolitiqueIn(BaseModel):
    nom: str = Field(min_length=3, max_length=120)
    description: str = Field(default="", max_length=1000)
    k_min: int = Field(default=5, ge=2, le=50)
    action: str = Field(default="AVERTIR", pattern="^(AVERTIR|SUPPRIMER|BLOQUER)$")
    max_lignes_export: int | None = Field(default=None, ge=1, le=5000)


class PolitiqueOut(Base):
    id: int
    nom: str
    description: str
    k_min: int
    action: str
    max_lignes_export: int | None
    par_defaut: bool
    cree_le: UTCDatetime


# --- Intégrité du journal (V2) ---
class AnomalieOut(Base):
    id: int
    motif: str


class IntegriteOut(Base):
    valide: bool
    nb_total: int
    nb_chainees: int
    nb_anterieures: int
    nb_anomalies: int
    premiere_anomalie: AnomalieOut | None = None
    empreinte_tete: str
    verifie_le: UTCDatetime
    avertissement: str
