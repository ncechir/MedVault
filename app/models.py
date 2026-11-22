"""Modèle de données du portail d'accès aux données de santé."""
from __future__ import annotations

import enum
import json
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import (
    Boolean, Date, DateTime, Enum, Float, ForeignKey, Integer, String, Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app import protections
from app.config import DELAI_PURGE_JOURS
from app.database import Base


def maintenant() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------
# Énumérations métier
# --------------------------------------------------------------------------
class Role(str, enum.Enum):
    CHERCHEUR = "CHERCHEUR"   # dépose des demandes
    DPO = "DPO"               # responsable de la protection des données
    ADMIN = "ADMIN"           # administration technique


class CategorieChamp(str, enum.Enum):
    IDENTIFIANT_DIRECT = "IDENTIFIANT_DIRECT"    # nom, prénom, IPP, NIR...
    QUASI_IDENTIFIANT = "QUASI_IDENTIFIANT"      # date de naissance, code postal...
    DONNEE_SANTE = "DONNEE_SANTE"                # diagnostic, traitement (art. 9 RGPD)
    ADMINISTRATIF = "ADMINISTRATIF"              # durée de séjour, service...
    DONNEE_PUBLIQUE = "DONNEE_PUBLIQUE"          # référentiels et statistiques ouverts


class ModeAcces(str, enum.Enum):
    BRUT = "BRUT"                  # valeur en clair
    PSEUDONYMISE = "PSEUDONYMISE"  # valeur remplacée par un pseudonyme stable
    AGREGE = "AGREGE"              # uniquement des statistiques


class StatutDemande(str, enum.Enum):
    BROUILLON = "BROUILLON"
    SOUMISE = "SOUMISE"
    EN_INSTRUCTION = "EN_INSTRUCTION"
    VALIDEE = "VALIDEE"
    REFUSEE = "REFUSEE"


class StatutAutorisation(str, enum.Enum):
    ACTIVE = "ACTIVE"
    EXPIREE = "EXPIREE"
    REVOQUEE = "REVOQUEE"
    PURGEE = "PURGEE"


class SensDecision(str, enum.Enum):
    VALIDEE = "VALIDEE"
    VALIDEE_SOUS_CONDITION = "VALIDEE_SOUS_CONDITION"
    REFUSEE = "REFUSEE"


class TypeNotification(str, enum.Enum):
    DECISION_VALIDEE = "DECISION_VALIDEE"
    DECISION_REFUSEE = "DECISION_REFUSEE"
    ACCES_BIENTOT_EXPIRE = "ACCES_BIENTOT_EXPIRE"
    ACCES_EXPIRE = "ACCES_EXPIRE"
    ACCES_REVOQUE = "ACCES_REVOQUE"


# --------------------------------------------------------------------------
# Tables
# --------------------------------------------------------------------------
class Utilisateur(Base):
    __tablename__ = "utilisateur"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    mot_de_passe_hash: Mapped[str] = mapped_column(String(255))
    nom_complet: Mapped[str] = mapped_column(String(180))
    service: Mapped[str] = mapped_column(String(120), default="")
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.CHERCHEUR)
    actif: Mapped[bool] = mapped_column(Boolean, default=True)
    cree_le: Mapped[datetime] = mapped_column(DateTime, default=maintenant)

    demandes: Mapped[list[Demande]] = relationship(
        back_populates="demandeur", foreign_keys="Demande.demandeur_id"
    )


class Patient(Base):
    """Patient de l'entrepôt d'études.

    Minimisation à la source : les colonnes d'identité (ipp, nom, prénom, numéro
    de sécurité sociale) sont facultatives et **restent vides** dans la base
    alimentée par le portail. L'identité reste dans le dossier de soins ; une
    étude interne n'en a jamais besoin. Le patient n'est désigné que par son
    identifiant technique, jamais transmis tel quel (voir pseudonymisation.py).
    """
    __tablename__ = "patient"

    id: Mapped[int] = mapped_column(primary_key=True)
    ipp: Mapped[str | None] = mapped_column(String(20), unique=True, index=True, nullable=True)
    nom: Mapped[str | None] = mapped_column(String(80), nullable=True)
    prenom: Mapped[str | None] = mapped_column(String(80), nullable=True)
    num_secu: Mapped[str | None] = mapped_column(String(20), nullable=True)
    date_naissance: Mapped[date] = mapped_column(Date)
    sexe: Mapped[str] = mapped_column(String(1))
    code_postal: Mapped[str] = mapped_column(String(5))
    commune: Mapped[str] = mapped_column(String(80))

    sejours: Mapped[list[Sejour]] = relationship(back_populates="patient")


class Sejour(Base):
    """Un passage hospitalier. C'est la table interrogée par les extractions."""
    __tablename__ = "sejour"

    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patient.id"), index=True)
    # Établissement où s'est déroulé le séjour (choisi par le chercheur à la demande)
    hopital_code: Mapped[str] = mapped_column(String(20), default="", index=True)
    service: Mapped[str] = mapped_column(String(60), index=True)
    date_entree: Mapped[date] = mapped_column(Date)
    duree_sejour: Mapped[int] = mapped_column(Integer)
    diagnostic_cim10: Mapped[str] = mapped_column(String(10))
    diagnostic_libelle: Mapped[str] = mapped_column(String(120), default="")
    traitements: Mapped[str] = mapped_column(String(200))
    mode_sortie: Mapped[str] = mapped_column(String(60))
    # Compte-rendu d'examen (biologie/imagerie) à l'origine du diagnostic
    resultat_analyse: Mapped[str] = mapped_column(Text, default="")
    motif_admission: Mapped[str] = mapped_column(String(120), default="")
    gravite_ccmu: Mapped[int] = mapped_column(Integer, default=0)
    attente_minutes: Mapped[int] = mapped_column(Integer, default=0)

    patient: Mapped[Patient] = relationship(back_populates="sejours")

    @property
    def diagnostic(self) -> str:
        """« I21 - Infarctus aigu du myocarde » : le code seul parle à peu de monde."""
        if self.diagnostic_libelle:
            return f"{self.diagnostic_cim10} - {self.diagnostic_libelle}"
        return self.diagnostic_cim10


class Hopital(Base):
    """Un établissement du territoire national.

    Sert à deux choses : filtrer les séjours par zone géographique ou par
    établissement précis à la demande, et porter les indicateurs territoriaux
    affichés sur la carte.
    """
    __tablename__ = "hopital"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    nom: Mapped[str] = mapped_column(String(160))
    ville: Mapped[str] = mapped_column(String(80))
    region: Mapped[str] = mapped_column(String(80), index=True)
    departement: Mapped[str] = mapped_column(String(3))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    population_bassin: Mapped[int] = mapped_column(Integer, default=0)


class IndicateurHopital(Base):
    """Indicateurs territoriaux annuels d'un établissement (synthétiques).

    Même logique qu'un observatoire régional de santé : taux standardisés déjà
    agrégés, aucun patient concerné. Alimente la carte et le lot « Indicateurs
    de santé par territoire ».
    """
    __tablename__ = "indicateur_hopital"
    __table_args__ = (UniqueConstraint("hopital_code", "annee"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    hopital_code: Mapped[str] = mapped_column(String(20), index=True)
    annee: Mapped[int] = mapped_column(Integer, index=True)
    taux_hospitalisation: Mapped[float] = mapped_column(Float)  # pour 100 000 hab.
    taux_mortalite: Mapped[float] = mapped_column(Float)        # pour 100 000 hab.
    hospitalisations_covid: Mapped[int] = mapped_column(Integer, default=0)


class EmailEnvoye(Base):
    """Trace de chaque e-mail rédigé par la plateforme.

    Sans serveur SMTP configuré, aucun message ne part réellement : cette
    table reste la seule preuve qu'il a bien été généré, avec son contenu
    exact. Avec un SMTP configuré, elle sert de journal d'envoi.
    """
    __tablename__ = "email_envoye"

    id: Mapped[int] = mapped_column(primary_key=True)
    destinataire: Mapped[str] = mapped_column(String(180), index=True)
    sujet: Mapped[str] = mapped_column(String(250))
    corps: Mapped[str] = mapped_column(Text)
    type_notification: Mapped[str] = mapped_column(String(40), default="")
    piece_jointe_nom: Mapped[str] = mapped_column(String(120), default="")
    statut: Mapped[str] = mapped_column(String(20), default="SIMULE")  # SIMULE, ENVOYE, ECHEC
    erreur: Mapped[str] = mapped_column(String(500), default="")
    cree_le: Mapped[datetime] = mapped_column(DateTime, default=maintenant)


class LigneGenerique(Base):
    """Une ligne d'un jeu de données importé tel quel par le délégué.

    Stockage en JSON plutôt qu'en colonnes dédiées : un fichier déposé par le
    délégué peut avoir n'importe quelle forme. L'extraction lit ces lignes et
    ne restitue que les colonnes effectivement demandées, comme pour les
    autres lots.
    """
    __tablename__ = "ligne_generique"

    id: Mapped[int] = mapped_column(primary_key=True)
    lot_id: Mapped[int] = mapped_column(ForeignKey("lot_donnees.id"), index=True)
    donnees_json: Mapped[str] = mapped_column(Text)


class MedicamentPathologie(Base):
    """Référentiel public : quel médicament (code CIS) traite quelle maladie.

    Aucune personne concernée : ce sont des données de référence, pas des
    dossiers de patients.
    """
    __tablename__ = "medicament_pathologie"

    id: Mapped[int] = mapped_column(primary_key=True)
    code_cis: Mapped[str] = mapped_column(String(12), index=True)
    pathologie: Mapped[str] = mapped_column(String(120), index=True)


class DecesStat(Base):
    """Statistiques nationales de causes de décès : déjà agrégées, publiques."""
    __tablename__ = "deces_stat"

    id: Mapped[int] = mapped_column(primary_key=True)
    annee: Mapped[int] = mapped_column(Integer, index=True)
    cause: Mapped[str] = mapped_column(String(200), index=True)
    sexe: Mapped[str] = mapped_column(String(20))
    classe_age: Mapped[str] = mapped_column(String(30))
    effectifs: Mapped[int | None] = mapped_column(Integer, nullable=True)
    taux_standardise: Mapped[float | None] = mapped_column(Float, nullable=True)
    age_median: Mapped[float | None] = mapped_column(Float, nullable=True)
    part_cause: Mapped[float | None] = mapped_column(Float, nullable=True)


class LotDonnees(Base):
    """Un ensemble de données réutilisable (un entrepôt, un extract...)."""
    __tablename__ = "lot_donnees"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(60), unique=True)
    libelle: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    responsable: Mapped[str] = mapped_column(String(180), default="")
    # Filtre appliqué sur sejour.service lors d'une extraction (vide = tous)
    service_source: Mapped[str] = mapped_column(String(60), default="")
    # D'où viennent les lignes : SEJOUR, MEDICAMENT, DECES, INDICATEUR ou GENERIQUE
    source_donnees: Mapped[str] = mapped_column(String(20), default="SEJOUR")
    # Renseigné pour un lot importé par le délégué (source_donnees=GENERIQUE)
    importe_par_id: Mapped[int | None] = mapped_column(
        ForeignKey("utilisateur.id"), nullable=True)
    importe_le: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    champs: Mapped[list[Champ]] = relationship(
        back_populates="lot", cascade="all, delete-orphan", order_by="Champ.id"
    )
    importe_par: Mapped["Utilisateur | None"] = relationship(foreign_keys=[importe_par_id])


class Champ(Base):
    """Une colonne d'un lot, qualifiée par sa catégorie RGPD."""
    __tablename__ = "champ"
    __table_args__ = (UniqueConstraint("lot_id", "code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    lot_id: Mapped[int] = mapped_column(ForeignKey("lot_donnees.id"))
    code: Mapped[str] = mapped_column(String(80))
    libelle: Mapped[str] = mapped_column(String(200))
    categorie: Mapped[CategorieChamp] = mapped_column(Enum(CategorieChamp))
    # D'où vient la valeur : "patient.nom", "sejour.duree_sejour", "calcul.age"
    source: Mapped[str] = mapped_column(String(60), default="")
    # Thème affiché à l'écran : « Maladie », « Traitement », « Profil du patient »...
    groupe: Mapped[str] = mapped_column(String(60), default="")

    lot: Mapped[LotDonnees] = relationship(back_populates="champs")

    @property
    def protection(self) -> str:
        """Ce que le demandeur reçoit par défaut, en langage courant."""
        return protections.description(self.categorie, self.code, self.source)

    @property
    def reductible(self) -> bool:
        return protections.reductible(self.categorie, self.code, self.source)


class Demande(Base):
    __tablename__ = "demande"

    id: Mapped[int] = mapped_column(primary_key=True)
    demandeur_id: Mapped[int] = mapped_column(ForeignKey("utilisateur.id"))
    lot_id: Mapped[int] = mapped_column(ForeignKey("lot_donnees.id"))

    titre_projet: Mapped[str] = mapped_column(String(200))
    finalite: Mapped[str] = mapped_column(Text)
    base_legale: Mapped[str] = mapped_column(String(200), default="Mission d'intérêt public (art. 6.1.e)")
    date_debut_souhaitee: Mapped[date] = mapped_column(Date)
    date_fin_souhaitee: Mapped[date] = mapped_column(Date)

    # Services hospitaliers concernés (liste JSON). Vide = tous les services.
    services_json: Mapped[str] = mapped_column(Text, default="[]")
    # Établissements choisis (codes Hopital.code). Vide = tout le territoire.
    hopitaux_json: Mapped[str] = mapped_column(Text, default="[]")

    statut: Mapped[StatutDemande] = mapped_column(
        Enum(StatutDemande), default=StatutDemande.BROUILLON, index=True
    )
    cree_le: Mapped[datetime] = mapped_column(DateTime, default=maintenant)
    soumise_le: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    demandeur: Mapped[Utilisateur] = relationship(
        back_populates="demandes", foreign_keys=[demandeur_id]
    )
    lot: Mapped[LotDonnees] = relationship()
    champs_demandes: Mapped[list[DemandeChamp]] = relationship(
        back_populates="demande", cascade="all, delete-orphan"
    )
    decision: Mapped[Decision | None] = relationship(
        back_populates="demande", uselist=False, cascade="all, delete-orphan"
    )
    autorisation: Mapped[Autorisation | None] = relationship(
        back_populates="demande", uselist=False, cascade="all, delete-orphan"
    )

    @property
    def duree_jours(self) -> int:
        return (self.date_fin_souhaitee - self.date_debut_souhaitee).days

    @property
    def services(self) -> list[str]:
        try:
            return list(json.loads(self.services_json or "[]"))
        except ValueError:
            return []

    @services.setter
    def services(self, valeur: list[str]) -> None:
        self.services_json = json.dumps(list(valeur), ensure_ascii=False)

    @property
    def hopitaux(self) -> list[str]:
        try:
            return list(json.loads(self.hopitaux_json or "[]"))
        except ValueError:
            return []

    @hopitaux.setter
    def hopitaux(self, valeur: list[str]) -> None:
        self.hopitaux_json = json.dumps(list(valeur), ensure_ascii=False)

    @property
    def reference(self) -> str:
        """Référence administrative d'un dossier, telle qu'on la citerait par écrit."""
        annee = (self.cree_le or maintenant()).year
        return f"DA-{annee}-{self.id:04d}"


class DemandeChamp(Base):
    """Quel champ, sous quelle forme. C'est ici que se joue la pseudonymisation."""
    __tablename__ = "demande_champ"
    __table_args__ = (UniqueConstraint("demande_id", "champ_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    demande_id: Mapped[int] = mapped_column(ForeignKey("demande.id"))
    champ_id: Mapped[int] = mapped_column(ForeignKey("champ.id"))
    mode: Mapped[ModeAcces] = mapped_column(Enum(ModeAcces), default=ModeAcces.PSEUDONYMISE)
    justification: Mapped[str] = mapped_column(Text, default="")

    demande: Mapped[Demande] = relationship(back_populates="champs_demandes")
    champ: Mapped[Champ] = relationship()

    @property
    def protection(self) -> str:
        """Ce que le demandeur recevra pour cette information, avec ce mode."""
        return protections.resultat(
            self.champ.categorie, self.champ.code, self.champ.source, self.mode)


class Decision(Base):
    __tablename__ = "decision"

    id: Mapped[int] = mapped_column(primary_key=True)
    demande_id: Mapped[int] = mapped_column(ForeignKey("demande.id"), unique=True)
    dpo_id: Mapped[int] = mapped_column(ForeignKey("utilisateur.id"))
    sens: Mapped[SensDecision] = mapped_column(Enum(SensDecision))
    motif: Mapped[str] = mapped_column(Text)
    conditions: Mapped[str] = mapped_column(Text, default="")
    date_fin_acces: Mapped[date | None] = mapped_column(Date, nullable=True)
    prise_le: Mapped[datetime] = mapped_column(DateTime, default=maintenant)

    demande: Mapped[Demande] = relationship(back_populates="decision")
    dpo: Mapped[Utilisateur] = relationship()


class Autorisation(Base):
    """Droit d'accès effectif, créé uniquement à la suite d'une décision favorable."""
    __tablename__ = "autorisation"

    id: Mapped[int] = mapped_column(primary_key=True)
    demande_id: Mapped[int] = mapped_column(ForeignKey("demande.id"), unique=True)
    date_debut: Mapped[date] = mapped_column(Date)
    date_fin: Mapped[date] = mapped_column(Date)
    statut: Mapped[StatutAutorisation] = mapped_column(
        Enum(StatutAutorisation), default=StatutAutorisation.ACTIVE, index=True
    )
    revoquee_le: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    motif_revocation: Mapped[str] = mapped_column(Text, default="")
    purge_effectuee_le: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    demande: Mapped[Demande] = relationship(back_populates="autorisation")

    @property
    def reference(self) -> str:
        return self.demande.reference

    @property
    def titre_projet(self) -> str:
        return self.demande.titre_projet

    @property
    def demandeur_nom(self) -> str:
        return self.demande.demandeur.nom_complet

    @property
    def decision(self) -> "Decision | None":
        return self.demande.decision

    @property
    def date_purge_prevue(self) -> date:
        """Date limite de suppression des données remises au chercheur."""
        return self.date_fin + timedelta(days=DELAI_PURGE_JOURS)


class Notification(Base):
    """Message adressé à un utilisateur : décision rendue, accès arrivant à terme."""
    __tablename__ = "notification"

    id: Mapped[int] = mapped_column(primary_key=True)
    destinataire_id: Mapped[int] = mapped_column(ForeignKey("utilisateur.id"), index=True)
    type: Mapped[TypeNotification] = mapped_column(Enum(TypeNotification), index=True)
    titre: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text)
    demande_id: Mapped[int | None] = mapped_column(ForeignKey("demande.id"), nullable=True)
    autorisation_id: Mapped[int | None] = mapped_column(
        ForeignKey("autorisation.id"), nullable=True
    )
    lue: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    cree_le: Mapped[datetime] = mapped_column(DateTime, default=maintenant, index=True)

    destinataire: Mapped[Utilisateur] = relationship()


class JournalAudit(Base):
    """Traçabilité : append-only, jamais modifié ni supprimé."""
    __tablename__ = "journal_audit"

    id: Mapped[int] = mapped_column(primary_key=True)
    horodatage: Mapped[datetime] = mapped_column(DateTime, default=maintenant, index=True)
    utilisateur_id: Mapped[int | None] = mapped_column(ForeignKey("utilisateur.id"), nullable=True)
    utilisateur_email: Mapped[str] = mapped_column(String(180), default="")
    action: Mapped[str] = mapped_column(String(80), index=True)
    entite: Mapped[str] = mapped_column(String(60))
    entite_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    details: Mapped[str] = mapped_column(Text, default="")
    # Chaînage des entrées (V2) : empreinte SHA-256 de l'entrée, calculée à partir
    # de l'empreinte de la précédente. Toute modification ou suppression d'une
    # entrée intermédiaire rompt la chaîne et se détecte à la vérification.
    # Nulles pour les entrées antérieures à l'introduction du chaînage.
    empreinte_precedente: Mapped[str | None] = mapped_column(String(64), nullable=True)
    empreinte: Mapped[str | None] = mapped_column(String(64), nullable=True)


class PolitiqueDonnees(Base):
    """Règles de confidentialité réutilisables, appliquées aux extractions (V2).

    Une seule politique est « par défaut » : c'est elle qui s'applique à toute
    extraction ou export. Le délégué en définit autant que nécessaire.
    """
    __tablename__ = "politique_donnees"

    id: Mapped[int] = mapped_column(primary_key=True)
    nom: Mapped[str] = mapped_column(String(120), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    # Taille minimale d'un groupe d'individus indiscernables (k-anonymat)
    k_min: Mapped[int] = mapped_column(Integer, default=5)
    # AVERTIR : on signale. SUPPRIMER : les lignes des petits groupes sont retirées.
    # BLOQUER : l'export est refusé tant que le seuil n'est pas atteint.
    action: Mapped[str] = mapped_column(String(12), default="AVERTIR")
    max_lignes_export: Mapped[int | None] = mapped_column(Integer, nullable=True)
    par_defaut: Mapped[bool] = mapped_column(Boolean, default=False)
    cree_par_id: Mapped[int | None] = mapped_column(ForeignKey("utilisateur.id"), nullable=True)
    cree_le: Mapped[datetime] = mapped_column(DateTime, default=maintenant)
