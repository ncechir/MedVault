"""Établissements et indicateurs territoriaux, à la manière d'un atlas régional
de santé (inspiré de l'observatoire SIRSé PACA : densité, hospitalisations,
mortalité, COVID-19). Toutes les valeurs sont synthétiques.

Module pur : aucune dépendance base de données.
"""
from __future__ import annotations

import random

# (code, nom, ville, région, département, latitude, longitude, population du bassin)
HOPITAUX: list[tuple] = [
    # Prototype : un seul établissement, dans les Alpes-Côte d'Azur.
    ("CHU-NICE", "CHU Sophia (Nice)", "Nice", "Provence-Alpes-Côte d'Azur", "06", 43.7148, 7.2760, 550_000),
]

REGIONS = sorted({h[3] for h in HOPITAUX})


def poids_frequentation(hopital: tuple) -> float:
    """La taille du bassin de population conditionne le nombre de séjours."""
    return hopital[7] / 100_000


def generer_indicateurs(alea: random.Random, hopital: tuple, annees: range) -> list[dict]:
    """Indicateurs annuels façon observatoire régional de santé.

    - taux d'hospitalisation et taux de mortalité pour 100 000 habitants,
      avec une variabilité territoriale plausible ;
    - hospitalisations liées au COVID-19, avec le pic 2020-2021 et la décrue
      ensuite, comme observé nationalement.
    """
    code = hopital[0]
    base_hospit = alea.uniform(1450, 2100)      # pour 100 000 hab.
    base_mortalite = alea.uniform(750, 1000)    # pour 100 000 hab.
    lignes = []
    for annee in annees:
        vague_covid = {2020: 1.0, 2021: 0.85, 2022: 0.35, 2023: 0.12, 2024: 0.08}.get(annee, 0.0)
        lignes.append({
            "code_hopital": code,
            "annee": annee,
            "taux_hospitalisation": round(base_hospit * alea.uniform(0.93, 1.07), 1),
            "taux_mortalite": round(base_mortalite * alea.uniform(0.92, 1.08), 1),
            "hospitalisations_covid": round(hopital[7] / 100_000 * vague_covid
                                            * alea.uniform(80, 140)),
        })
    return lignes


def assigner_hopital(alea: random.Random, hopitaux: list, service: str) -> str:
    """Tire un hôpital pour un séjour, pondéré par la taille du bassin.

    Un service de pointe (réanimation, oncologie...) est plus souvent rattaché
    à un CHU ; un service courant se répartit sur tout le territoire.
    """
    candidats = hopitaux
    if service in ("Réanimation", "Oncologie", "Neurologie", "Hématologie",
                   "Chirurgie vasculaire", "Néphrologie"):
        chu = [h for h in hopitaux if h[0].startswith(("CHU", "AP-HP"))]
        candidats = chu or hopitaux
    return alea.choices(candidats, weights=[poids_frequentation(h) for h in candidats])[0][0]
