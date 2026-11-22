"""Production d'une extraction à partir d'une autorisation active.

Principe : la demande déclare ce qu'elle veut ; c'est ici que les protections
sont **réellement appliquées** aux données. Rien ne sort de l'entrepôt sans
passer par cette fonction.

Cinq familles de jeux de données, selon `lot.source_donnees` :
- SEJOUR : séjours de patients (synthétiques), protégés colonne par colonne ;
- MEDICAMENT et DECES : référentiels publics, sans personne concernée ;
- INDICATEUR : indicateurs territoriaux par établissement, déjà agrégés ;
- GENERIQUE : jeu importé par le délégué, protégé selon la catégorie choisie
  au moment de l'import (une seule catégorie pour tout le fichier).
"""
import json
from collections import Counter
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import protections
from app import pseudonymisation as pseudo
from app.models import (
    CategorieChamp, DecesStat, Demande, Hopital, IndicateurHopital,
    LigneGenerique, MedicamentPathologie, ModeAcces, Patient, Sejour,
)

LIMITE_PAR_DEFAUT = 100
LIMITE_MAX = 5000

# Jeux de référence : table source et ordre de lecture
TABLES_REFERENCE = {
    "MEDICAMENT": (MedicamentPathologie, (MedicamentPathologie.code_cis,
                                          MedicamentPathologie.pathologie)),
    "DECES": (DecesStat, (DecesStat.annee.desc(), DecesStat.cause,
                          DecesStat.sexe, DecesStat.classe_age)),
}


class ExtractionRefusee(Exception):
    """Levée quand une extraction violerait une règle de protection."""


def _hopitaux_par_code(db: Session) -> dict[str, Hopital]:
    return {h.code: h for h in db.scalars(select(Hopital)).all()}


def _valeur_source(sejour: Sejour, source: str, hopitaux: dict[str, Hopital] | None = None):
    """Résout 'patient.nom', 'sejour.duree_sejour', 'calcul.age' ou 'hopital.nom'."""
    table, _, attribut = source.partition(".")
    if table == "patient":
        return getattr(sejour.patient, attribut, None)
    if table == "sejour":
        return getattr(sejour, attribut, None)
    if table == "calcul" and attribut == "age":
        return pseudo.calculer_age(sejour.patient.date_naissance, sejour.date_entree)
    if table == "calcul" and attribut == "departement":
        cp = str(sejour.patient.code_postal or "")
        return cp[:2] if len(cp) >= 2 else ""
    if table == "hopital" and hopitaux is not None:
        hopital = hopitaux.get(sejour.hopital_code)
        return getattr(hopital, attribut, None) if hopital else None
    return None


def _texte(valeur) -> str:
    return "" if valeur is None else str(valeur)


def _transformer(valeur, champ, mode: ModeAcces, sel: bytes,
                 sejour: Sejour) -> tuple[str, str]:
    """Renvoie (valeur affichée, nom de la transformation appliquée)."""
    categorie = champ.categorie

    if categorie == CategorieChamp.IDENTIFIANT_DIRECT:
        if mode == ModeAcces.BRUT:
            # Filet de sécurité : ce cas est déjà bloqué par la règle R2 à la
            # soumission et à la validation. S'il arrive ici, c'est une faille.
            raise ExtractionRefusee(
                f"Identifiant direct « {champ.libelle} » demandé en clair."
            )
        # Le jeton est dérivé de l'identité du patient, jamais de la valeur de
        # la colonne : sinon deux homonymes sans lien recevraient le même
        # pseudonyme et seraient analysés comme une seule personne.
        return pseudo.pseudonymiser(sejour.patient_id, sel, "PAT"), protections.CODE_ANONYME

    if categorie == CategorieChamp.QUASI_IDENTIFIANT and mode != ModeAcces.BRUT:
        if champ.code == "date_entree" and isinstance(valeur, date):
            return pseudo.generaliser_mois(valeur), protections.MOIS
        if isinstance(valeur, date):
            return pseudo.generaliser_date(valeur), protections.ANNEE
        if champ.code == "departement":
            # Déjà réduit à la source (calcul.departement) : aucune généralisation
            # supplémentaire à appliquer, le code postal n'est jamais exposé.
            return _texte(valeur), protections.DEPARTEMENT
        if champ.code in ("code_postal", "cp"):
            return pseudo.generaliser_code_postal(valeur), protections.DEPARTEMENT
        if champ.code == "age":
            return pseudo.generaliser_age(valeur), protections.TRANCHE_AGE
        if champ.code == "commune":
            return pseudo.masquer(), protections.MASQUE
        return _texte(valeur), protections.VALEUR_EXACTE

    return _texte(valeur), protections.VALEUR_EXACTE


def _colonnes(detail, transformations: dict) -> list[dict]:
    return [{
        "code": liaison.champ.code,
        "libelle": liaison.champ.libelle,
        "categorie": liaison.champ.categorie.value,
        "mode": liaison.mode.value,
        "groupe": liaison.champ.groupe,
        "transformation": transformations.get(liaison.champ.code, protections.VALEUR_EXACTE),
    } for liaison in detail]


def _effectifs(agreges, valeurs_de) -> list[dict]:
    """Colonnes demandées en agrégé : jamais au niveau ligne, seulement en effectifs."""
    statistiques = []
    for liaison in agreges:
        compteur = Counter(valeurs_de(liaison))
        for valeur, effectif in compteur.most_common(20):
            statistiques.append({
                "colonne": liaison.champ.libelle,
                "valeur": valeur,
                "effectif": effectif,
            })
    return statistiques


def _services_concernes(demande: Demande) -> list[str]:
    """La définition du lot prime ; sinon les services choisis dans la demande."""
    if demande.lot.service_source:
        return [demande.lot.service_source]
    return demande.services


def _produire_sejours(db: Session, demande: Demande, limite: int) -> dict:
    sel = pseudo.sel_de_demande(demande.id)
    liaisons = list(demande.champs_demandes)
    detail = [x for x in liaisons if x.mode != ModeAcces.AGREGE]
    agreges = [x for x in liaisons if x.mode == ModeAcces.AGREGE]

    requete = select(Sejour).join(Patient)
    comptage = select(func.count(Sejour.id))
    services = _services_concernes(demande)
    if services:
        requete = requete.where(Sejour.service.in_(services))
        comptage = comptage.where(Sejour.service.in_(services))
    if demande.hopitaux:
        requete = requete.where(Sejour.hopital_code.in_(demande.hopitaux))
        comptage = comptage.where(Sejour.hopital_code.in_(demande.hopitaux))
    nb_total = db.scalar(comptage) or 0
    sejours = db.scalars(
        requete.order_by(Sejour.date_entree.desc(), Sejour.id).limit(limite)
    ).all()
    hopitaux = _hopitaux_par_code(db)

    transformations, lignes = {}, []
    for sejour in sejours:
        ligne = {}
        for liaison in detail:
            brute = _valeur_source(sejour, liaison.champ.source, hopitaux)
            affichee, transformation = _transformer(
                brute, liaison.champ, liaison.mode, sel, sejour
            )
            ligne[liaison.champ.code] = affichee
            transformations[liaison.champ.code] = transformation
        lignes.append(ligne)

    # Même en agrégé, un identifiant ou un quasi-identifiant ne sort jamais
    # brut : on compte les jetons et les valeurs généralisées.
    statistiques = _effectifs(agreges, lambda liaison: (
        _transformer(_valeur_source(s, liaison.champ.source, hopitaux), liaison.champ,
                     ModeAcces.PSEUDONYMISE, sel, s)[0]
        for s in sejours
    ))
    return {"lignes": lignes, "colonnes": _colonnes(detail, transformations),
            "statistiques": statistiques, "nb_total": nb_total}


def _produire_reference(db: Session, demande: Demande, limite: int) -> dict:
    """Jeux publics : aucune personne concernée, donc aucune transformation."""
    modele, ordre = TABLES_REFERENCE[demande.lot.source_donnees]
    liaisons = list(demande.champs_demandes)
    detail = [x for x in liaisons if x.mode != ModeAcces.AGREGE]
    agreges = [x for x in liaisons if x.mode == ModeAcces.AGREGE]

    nb_total = db.scalar(select(func.count()).select_from(modele)) or 0
    rows = db.scalars(select(modele).order_by(*ordre).limit(limite)).all()

    def valeur(row, liaison):
        return _texte(getattr(row, liaison.champ.source.partition(".")[2], None))

    lignes = [{x.champ.code: valeur(r, x) for x in detail} for r in rows]
    statistiques = _effectifs(
        agreges, lambda liaison: (valeur(r, liaison) for r in rows))
    return {"lignes": lignes, "colonnes": _colonnes(detail, {}),
            "statistiques": statistiques, "nb_total": nb_total}


def _produire_indicateur(db: Session, demande: Demande, limite: int) -> dict:
    """Indicateurs territoriaux : déjà agrégés, aucune personne concernée."""
    liaisons = list(demande.champs_demandes)
    detail = [x for x in liaisons if x.mode != ModeAcces.AGREGE]
    agreges = [x for x in liaisons if x.mode == ModeAcces.AGREGE]

    requete = select(IndicateurHopital)
    comptage = select(func.count(IndicateurHopital.id))
    if demande.hopitaux:
        requete = requete.where(IndicateurHopital.hopital_code.in_(demande.hopitaux))
        comptage = comptage.where(IndicateurHopital.hopital_code.in_(demande.hopitaux))
    nb_total = db.scalar(comptage) or 0
    rows = db.scalars(
        requete.order_by(IndicateurHopital.annee.desc(), IndicateurHopital.hopital_code)
               .limit(limite)
    ).all()
    hopitaux = _hopitaux_par_code(db)

    def valeur(row, liaison):
        table, _, attribut = liaison.champ.source.partition(".")
        if table == "hopital":
            hopital = hopitaux.get(row.hopital_code)
            return _texte(getattr(hopital, attribut, None) if hopital else None)
        return _texte(getattr(row, attribut, None))

    lignes = [{x.champ.code: valeur(r, x) for x in detail} for r in rows]
    statistiques = _effectifs(agreges, lambda liaison: (valeur(r, liaison) for r in rows))
    return {"lignes": lignes, "colonnes": _colonnes(detail, {}),
            "statistiques": statistiques, "nb_total": nb_total}


def _produire_generique(db: Session, demande: Demande, limite: int) -> dict:
    """Jeu importé par le délégué : lignes JSON, protégées selon la catégorie choisie."""
    liaisons = list(demande.champs_demandes)
    detail = [x for x in liaisons if x.mode != ModeAcces.AGREGE]
    agreges = [x for x in liaisons if x.mode == ModeAcces.AGREGE]

    nb_total = db.scalar(
        select(func.count(LigneGenerique.id)).where(LigneGenerique.lot_id == demande.lot_id)
    ) or 0
    rows = db.scalars(
        select(LigneGenerique).where(LigneGenerique.lot_id == demande.lot_id)
               .order_by(LigneGenerique.id).limit(limite)
    ).all()
    donnees = [json.loads(r.donnees_json or "{}") for r in rows]

    def valeur(ligne, liaison):
        return _texte(ligne.get(liaison.champ.code))

    lignes = [{x.champ.code: valeur(d, x) for x in detail} for d in donnees]
    statistiques = _effectifs(agreges, lambda liaison: (valeur(d, liaison) for d in donnees))
    return {"lignes": lignes, "colonnes": _colonnes(detail, {}),
            "statistiques": statistiques, "nb_total": nb_total}


def produire(db: Session, demande: Demande, limite: int = LIMITE_PAR_DEFAUT) -> dict:
    limite = max(1, min(limite, LIMITE_MAX))
    source = demande.lot.source_donnees
    if source == "INDICATEUR":
        resultat = _produire_indicateur(db, demande, limite)
    elif source == "GENERIQUE":
        resultat = _produire_generique(db, demande, limite)
    elif source in TABLES_REFERENCE:
        resultat = _produire_reference(db, demande, limite)
    else:
        resultat = _produire_sejours(db, demande, limite)

    return {
        "demande_id": demande.id,
        "titre_projet": demande.titre_projet,
        "lot": demande.lot.libelle,
        "produite_le": date.today(),
        "nb_lignes": len(resultat["lignes"]),
        "nb_total": resultat["nb_total"],
        # Garanti par le filet de sécurité de _transformer : un identifiant
        # direct en clair lève ExtractionRefusee avant d'arriver ici.
        "identites_masquees": True,
        "colonnes": resultat["colonnes"],
        "lignes": resultat["lignes"],
        "statistiques": resultat["statistiques"],
    }
