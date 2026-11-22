"""Techniques de protection appliquées aux extractions.

Deux familles distinctes, souvent confondues :

- la **pseudonymisation** remplace un identifiant par un jeton stable. Les
  lignes d'un même patient restent regroupables, mais le nom ne sort jamais.
- la **généralisation** dégrade la précision d'un quasi-identifiant
  (date de naissance → année, code postal → département) pour empêcher la
  ré-identification par croisement.

Le sel est dérivé de l'identifiant de la demande : deux études obtiennent des
pseudonymes différents pour le même patient, ce qui interdit de fusionner deux
extractions pour reconstituer un dossier complet. C'est le cloisonnement exigé
par le principe de minimisation.
"""
import hashlib
import hmac
from datetime import date

from app.config import SECRET_KEY

TRANCHES_AGE = 5  # amplitude des tranches d'âge, en années


def sel_de_demande(demande_id: int) -> bytes:
    """Sel propre à une demande, dérivé de la clé du service."""
    return hmac.new(
        SECRET_KEY.encode(), f"demande:{demande_id}".encode(), hashlib.sha256
    ).digest()


def pseudonymiser(valeur, sel: bytes, prefixe: str = "PSEUDO") -> str:
    """Jeton stable et non réversible : même entrée + même sel = même sortie."""
    if valeur is None:
        return ""
    jeton = hmac.new(sel, str(valeur).encode(), hashlib.sha256).hexdigest()
    return f"{prefixe}-{jeton[:10].upper()}"


def generaliser_date(valeur) -> str:
    """Ne conserve que l'année."""
    return str(valeur.year) if isinstance(valeur, date) else ""


def generaliser_mois(valeur) -> str:
    """Ne conserve que le mois et l'année (AAAA-MM)."""
    return valeur.strftime("%Y-%m") if isinstance(valeur, date) else ""


def generaliser_code_postal(valeur) -> str:
    """Ne conserve que le département."""
    texte = str(valeur or "")
    return f"{texte[:2]}***" if len(texte) >= 2 else ""


def generaliser_age(valeur) -> str:
    """Regroupe en tranches, avec un plafond pour les grands âges.

    Le plafond évite qu'un centenaire soit identifiable à lui seul.
    """
    try:
        age = int(valeur)
    except (TypeError, ValueError):
        return ""
    if age >= 90:
        return "90 et plus"
    borne = (age // TRANCHES_AGE) * TRANCHES_AGE
    return f"{borne}-{borne + TRANCHES_AGE - 1}"


def masquer(_valeur=None) -> str:
    """Supprime complètement la valeur."""
    return "(masqué)"


def calculer_age(naissance: date, reference: date | None = None) -> int:
    reference = reference or date.today()
    return (
        reference.year - naissance.year
        - ((reference.month, reference.day) < (naissance.month, naissance.day))
    )
