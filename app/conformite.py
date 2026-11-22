"""Moteur de contrôle de conformité RGPD.

C'est le composant qui remplace la validation « par email sans vérification
claire » décrite dans le sujet. Il analyse une demande et produit des alertes.

Une alerte BLOQUANTE interdit la soumission et la validation.
Une alerte AVERTISSEMENT doit être arbitrée explicitement par le DPO.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

from app.config import (
    DUREE_ACCES_MAX_MOIS,
    LONGUEUR_FINALITE_MIN,
    NB_CHAMPS_ALERTE,
    NB_QUASI_IDENTIFIANTS_ALERTE,
)
from app.models import CategorieChamp, Demande, ModeAcces

BLOQUANT = "BLOQUANT"
AVERTISSEMENT = "AVERTISSEMENT"


@dataclass
class Alerte:
    niveau: str
    code: str
    message: str
    reference: str  # texte de référence (article RGPD, AI Act, règle interne)

    def dict(self) -> dict:
        return asdict(self)


def analyser(demande: Demande) -> list[Alerte]:
    alertes: list[Alerte] = []
    liaisons = list(demande.champs_demandes)

    # R1 — Aucun champ demandé
    if not liaisons:
        alertes.append(Alerte(
            BLOQUANT, "R1_AUCUN_CHAMP",
            "La demande ne porte sur aucun champ.",
            "Règle interne",
        ))

    # R2 — Identité en clair : la règle centrale du sujet
    identifiants_bruts = [
        l for l in liaisons
        if l.champ.categorie == CategorieChamp.IDENTIFIANT_DIRECT
        and l.mode == ModeAcces.BRUT
    ]
    if identifiants_bruts:
        noms = ", ".join(l.champ.libelle for l in identifiants_bruts)
        alertes.append(Alerte(
            BLOQUANT, "R2_IDENTITE_EN_CLAIR",
            f"Identifiants directs demandés en clair : {noms}. "
            "Les identités doivent être pseudonymisées pour une étude interne.",
            "RGPD art. 4(5) et 32 — pseudonymisation",
        ))

    # R3 — Durée de conservation
    if demande.duree_jours <= 0:
        alertes.append(Alerte(
            BLOQUANT, "R3_DATES_INCOHERENTES",
            "La date de fin d'accès doit être postérieure à la date de début.",
            "RGPD art. 5.1.e — limitation de la conservation",
        ))
    elif demande.duree_jours > DUREE_ACCES_MAX_MOIS * 30:
        alertes.append(Alerte(
            BLOQUANT, "R3_DUREE_EXCESSIVE",
            f"Durée demandée de {demande.duree_jours} jours, "
            f"maximum autorisé {DUREE_ACCES_MAX_MOIS} mois.",
            "RGPD art. 5.1.e — limitation de la conservation",
        ))

    # R4 — Finalité explicite
    if len(demande.finalite.strip()) < LONGUEUR_FINALITE_MIN:
        alertes.append(Alerte(
            BLOQUANT, "R4_FINALITE_IMPRECISE",
            "La finalité est trop succincte pour être évaluée "
            f"(minimum {LONGUEUR_FINALITE_MIN} caractères).",
            "RGPD art. 5.1.b — finalité déterminée et explicite",
        ))

    # R5 — Croisement de quasi-identifiants (risque de ré-identification)
    quasi = [
        l for l in liaisons
        if l.champ.categorie == CategorieChamp.QUASI_IDENTIFIANT
        and l.mode == ModeAcces.BRUT
    ]
    if len(quasi) >= NB_QUASI_IDENTIFIANTS_ALERTE:
        noms = ", ".join(l.champ.libelle for l in quasi)
        alertes.append(Alerte(
            AVERTISSEMENT, "R5_RISQUE_REIDENTIFICATION",
            f"{len(quasi)} quasi-identifiants demandés en clair ({noms}). "
            "Leur croisement peut permettre de ré-identifier un patient.",
            "RGPD cons. 26 — risque de ré-identification",
        ))

    # R6 — Minimisation
    if len(liaisons) > NB_CHAMPS_ALERTE:
        alertes.append(Alerte(
            AVERTISSEMENT, "R6_MINIMISATION",
            f"{len(liaisons)} champs demandés. Vérifier que chacun est "
            "nécessaire à la finalité déclarée.",
            "RGPD art. 5.1.c — minimisation des données",
        ))

    # R7 — Données de santé en clair sans justification
    sante_sans_justif = [
        l for l in liaisons
        if l.champ.categorie == CategorieChamp.DONNEE_SANTE
        and l.mode == ModeAcces.BRUT
        and len(l.justification.strip()) < 10
    ]
    if sante_sans_justif:
        noms = ", ".join(l.champ.libelle for l in sante_sans_justif)
        alertes.append(Alerte(
            AVERTISSEMENT, "R7_SANTE_SANS_JUSTIFICATION",
            f"Données de santé demandées en clair sans justification : {noms}.",
            "RGPD art. 9 — catégories particulières de données",
        ))

    # R9 — Périmètre : « tous les services » doit rester une exception assumée
    lot = demande.lot
    if (lot.source_donnees == "SEJOUR" and not lot.service_source
            and not demande.services):
        alertes.append(Alerte(
            AVERTISSEMENT, "R9_TOUS_LES_SERVICES",
            "Aucun service précisé : la demande porte sur tous les services de "
            "l'hôpital. Vérifier que c'est nécessaire à la finalité.",
            "RGPD art. 5.1.c — minimisation des données",
        ))

    # R8 — Qualité des données (AI Act) : tout en agrégé n'a pas de sens
    #      pour une étude nécessitant un suivi individuel
    if liaisons and all(l.mode == ModeAcces.AGREGE for l in liaisons):
        alertes.append(Alerte(
            AVERTISSEMENT, "R8_QUALITE_AGREGATION",
            "Tous les champs sont demandés sous forme agrégée : vérifier que "
            "les statistiques produites resteront exploitables.",
            "AI Act art. 10 — qualité des données",
        ))

    return alertes


def bloquants(alertes: list[Alerte]) -> list[Alerte]:
    return [a for a in alertes if a.niveau == BLOQUANT]


def rapport(demande: Demande) -> dict:
    alertes = analyser(demande)
    blocs = bloquants(alertes)
    identifiants = [
        l for l in demande.champs_demandes
        if l.champ.categorie == CategorieChamp.IDENTIFIANT_DIRECT
    ]
    en_clair = [l for l in identifiants if l.mode == ModeAcces.BRUT]
    return {
        "demande_id": demande.id,
        "conforme": not blocs,
        "nb_bloquants": len(blocs),
        "nb_avertissements": len(alertes) - len(blocs),
        "identites_masquees": not en_clair,
        "nb_identifiants_masques": len(identifiants) - len(en_clair),
        "alertes": [a.dict() for a in alertes],
    }
