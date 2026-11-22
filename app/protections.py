"""Ce que le demandeur reçoit réellement, dit en langage courant.

Module volontairement pur (aucune dépendance base de données) : c'est la seule
source des libellés de protection. Le moteur d'extraction, le catalogue et
l'écran de demande s'appuient tous dessus, donc ce qui est annoncé à l'écran
est exactement ce qui est appliqué aux données.
"""

IDENTIFIANT_DIRECT = "IDENTIFIANT_DIRECT"
QUASI_IDENTIFIANT = "QUASI_IDENTIFIANT"
DONNEE_SANTE = "DONNEE_SANTE"
ADMINISTRATIF = "ADMINISTRATIF"
DONNEE_PUBLIQUE = "DONNEE_PUBLIQUE"

CODE_ANONYME = "Code anonyme"
VALEUR_EXACTE = "Valeur exacte"
ANNEE = "Année seulement"
MOIS = "Mois et année"
DEPARTEMENT = "Département seulement"
TRANCHE_AGE = "Tranche d'âge de 5 ans"
MASQUE = "Masqué"
COMPTAGES = "Comptages seulement"


def _texte(valeur) -> str:
    """Accepte une chaîne ou une énumération (dont la valeur est une chaîne)."""
    return str(getattr(valeur, "value", valeur))


def version_reduite(code: str, source: str = "") -> str | None:
    """Libellé de la version réduite d'un quasi-identifiant, ou None s'il n'y en a pas."""
    if code == "date_entree":
        return MOIS
    if code in ("code_postal", "cp"):
        return DEPARTEMENT
    if code == "age":
        return TRANCHE_AGE
    if code == "commune":
        return MASQUE
    if code in ("date_naissance", "ddn") or source.endswith("date_naissance"):
        return ANNEE
    return None


def description(categorie, code: str, source: str = "") -> str:
    """Ce que le demandeur reçoit par défaut pour cette information."""
    cat = _texte(categorie)
    if cat == IDENTIFIANT_DIRECT:
        return CODE_ANONYME
    if cat == QUASI_IDENTIFIANT:
        # Le département est déjà la seule forme proposée : il n'existe pas de
        # code postal en clair à réduire davantage.
        if code == "departement":
            return DEPARTEMENT
        return version_reduite(code, source) or VALEUR_EXACTE
    return VALEUR_EXACTE


def reductible(categorie, code: str, source: str = "") -> bool:
    """Vrai si l'information existe aussi en version réduite (donc peut être demandée exacte)."""
    return (_texte(categorie) == QUASI_IDENTIFIANT
            and version_reduite(code, source) is not None)


def resultat(categorie, code: str, source: str, mode) -> str:
    """Ce que le demandeur recevra pour une information et un mode choisis."""
    cat, mode = _texte(categorie), _texte(mode)
    if mode == "AGREGE":
        return COMPTAGES
    if cat == IDENTIFIANT_DIRECT:
        return "Refusé : identité en clair" if mode == "BRUT" else CODE_ANONYME
    if cat == QUASI_IDENTIFIANT and mode != "BRUT":
        if code == "departement":
            return DEPARTEMENT
        return version_reduite(code, source) or VALEUR_EXACTE
    return VALEUR_EXACTE
