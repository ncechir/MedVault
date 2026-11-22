"""Contrôle de confidentialité avant export.

Mesure le risque de ré-identification des lignes réellement livrées, par le
k-anonymat : les lignes qui partagent exactement les mêmes valeurs de
quasi-identifiants forment un groupe ; plus un groupe est petit, plus ses
membres sont faciles à reconnaître. Un groupe de taille 1 est une personne
unique dans le fichier.

Ce contrôle est une aide à la décision, pas une garantie juridique
d'anonymisation : il ne voit que les colonnes livrées, pas les données
détenues par un tiers qui pourraient être croisées.
"""
from collections import Counter
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PolitiqueDonnees

ACTIONS = ("AVERTIR", "SUPPRIMER", "BLOQUER")
K_DEFAUT = 5


@dataclass
class Politique:
    id: int | None = None
    nom: str = "Politique intégrée (k = 5, avertissement)"
    k_min: int = K_DEFAUT
    action: str = "AVERTIR"
    max_lignes_export: int | None = None


def politique_active(db: Session) -> Politique:
    p = db.scalar(select(PolitiqueDonnees).where(PolitiqueDonnees.par_defaut.is_(True))
                  .limit(1))
    if not p:
        return Politique()
    return Politique(id=p.id, nom=p.nom, k_min=p.k_min, action=p.action,
                     max_lignes_export=p.max_lignes_export)


def _groupes(lignes: list[dict], codes: list[str]) -> Counter:
    return Counter(tuple(l.get(c, "") for c in codes) for l in lignes)


def evaluer(colonnes: list[dict], lignes: list[dict], k: int) -> dict:
    quasi = [c for c in colonnes if c["categorie"] == "QUASI_IDENTIFIANT"]
    codes = [c["code"] for c in quasi]
    base = {"k_cible": k, "nb_lignes": len(lignes),
            "quasi_identifiants": [c["libelle"] for c in quasi]}

    if not lignes or not codes:
        return {**base, "score": 0, "niveau": "FAIBLE", "k_min": None,
                "nb_lignes_a_risque": 0, "nb_uniques": 0,
                "messages": ["Aucun quasi-identifiant dans les colonnes livrées : "
                             "pas de risque de ré-identification par recoupement "
                             "de ces champs."]}

    tailles = _groupes(lignes, codes)
    k_min = min(tailles.values())
    a_risque = sum(n for n in tailles.values() if n < k)
    uniques = sum(1 for n in tailles.values() if n == 1)
    total = len(lignes)

    score = min(100, round(100 * (0.6 * a_risque / total + 0.4 * uniques / total)))
    if k_min >= k:
        niveau = "FAIBLE"
    elif k_min < 2 or a_risque / total >= 0.2:
        niveau = "ELEVE"
    else:
        niveau = "MODERE"

    messages = []
    if k_min >= k:
        messages.append(f"Chaque combinaison de quasi-identifiants concerne au moins "
                        f"{k} lignes : le seuil est respecté.")
    else:
        messages.append(f"{a_risque} ligne(s) sur {total} appartiennent à un groupe de "
                        f"moins de {k} personnes indiscernables.")
        if uniques:
            messages.append(f"{uniques} ligne(s) sont uniques : la personne peut être "
                            f"reconnue par recoupement.")
    return {**base, "score": score, "niveau": niveau, "k_min": k_min,
            "nb_lignes_a_risque": a_risque, "nb_uniques": uniques, "messages": messages}


def appliquer(db: Session, resultat: dict, *, export: bool) -> dict:
    """Applique la politique active au résultat d'une extraction.

    Retourne le résultat (éventuellement filtré) avec une clé « controle ».
    Lève `ExportBloque` si la politique l'impose pour un export.
    """
    politique = politique_active(db)
    k = politique.k_min
    colonnes = resultat["colonnes"]
    codes = [c["code"] for c in colonnes if c["categorie"] == "QUASI_IDENTIFIANT"]

    controle = evaluer(colonnes, resultat["lignes"], k)
    controle.update({"politique": politique.nom, "action": politique.action,
                     "nb_lignes_supprimees": 0, "nb_agregats_supprimes": 0,
                     "bloque": False})

    sortie = dict(resultat)
    if politique.action == "SUPPRIMER":
        if codes and controle["k_min"] is not None and controle["k_min"] < k:
            tailles = _groupes(resultat["lignes"], codes)
            gardees = [l for l in resultat["lignes"]
                       if tailles[tuple(l.get(c, "") for c in codes)] >= k]
            controle["nb_lignes_supprimees"] = len(resultat["lignes"]) - len(gardees)
            sortie["lignes"] = gardees
            sortie["nb_lignes"] = len(gardees)
            controle["messages"].append(
                f"{controle['nb_lignes_supprimees']} ligne(s) retirée(s) par la "
                f"politique « {politique.nom} ».")
        stats = [s for s in resultat["statistiques"] if s["effectif"] >= k]
        controle["nb_agregats_supprimes"] = len(resultat["statistiques"]) - len(stats)
        sortie["statistiques"] = stats
        if controle["nb_agregats_supprimes"]:
            controle["messages"].append(
                f"{controle['nb_agregats_supprimes']} effectif(s) inférieur(s) à {k} "
                f"masqué(s).")
    elif politique.action == "BLOQUER":
        if controle["niveau"] != "FAIBLE":
            controle["bloque"] = True
            controle["messages"].append(
                f"Export refusé par la politique « {politique.nom} » tant que chaque "
                f"groupe ne compte pas au moins {k} lignes.")
            if export:
                raise ExportBloque(controle["messages"][-1], controle)

    if export and politique.max_lignes_export and \
            len(sortie["lignes"]) > politique.max_lignes_export:
        sortie["lignes"] = sortie["lignes"][:politique.max_lignes_export]
        sortie["nb_lignes"] = len(sortie["lignes"])
        controle["messages"].append(
            f"Export limité à {politique.max_lignes_export} lignes par la politique.")

    sortie["controle"] = controle
    return sortie


class ExportBloque(Exception):
    def __init__(self, message: str, controle: dict):
        super().__init__(message)
        self.controle = controle
