"""Établissements et indicateurs territoriaux, à la manière d'un atlas régional
de santé (inspiré de l'observatoire SIRSé PACA : densité, hospitalisations,
mortalité, COVID-19). Toutes les valeurs sont synthétiques.

Module pur : aucune dépendance base de données.
"""
from __future__ import annotations

import random

# (code, nom, ville, région, département, latitude, longitude, population du bassin)
HOPITAUX: list[tuple] = [
    ("CHU-NICE",      "CHU de Nice - Pasteur",            "Nice",             "Provence-Alpes-Côte d'Azur", "06", 43.7148, 7.2760, 550_000),
    ("CHU-MARSEILLE", "CHU de Marseille - La Timone",       "Marseille",        "Provence-Alpes-Côte d'Azur", "13", 43.2848, 5.4108, 1_050_000),
    ("CH-TOULON",     "Centre Hospitalier de Toulon",       "Toulon",           "Provence-Alpes-Côte d'Azur", "83", 43.1367, 5.9280, 430_000),
    ("CH-AVIGNON",    "Centre Hospitalier d'Avignon",       "Avignon",          "Provence-Alpes-Côte d'Azur", "84", 43.9352, 4.8222, 290_000),
    ("CH-GAP",        "Centre Hospitalier de Gap",          "Gap",              "Provence-Alpes-Côte d'Azur", "05", 44.5599, 6.0797, 140_000),
    ("CHU-BORDEAUX",  "CHU de Bordeaux - Pellegrin",         "Bordeaux",         "Nouvelle-Aquitaine",         "33", 44.8115, -0.6067, 980_000),
    ("CH-LIMOGES",    "CHU de Limoges - Dupuytren",          "Limoges",          "Nouvelle-Aquitaine",         "87", 45.8534, 1.2445, 310_000),
    ("CH-PAU",        "Centre Hospitalier de Pau",           "Pau",              "Nouvelle-Aquitaine",         "64", 43.3050, -0.3700, 260_000),
    ("CHU-TOULOUSE",  "CHU de Toulouse - Rangueil",          "Toulouse",         "Occitanie",                   "31", 43.5615, 1.4442, 900_000),
    ("CHU-MONTPELLIER","CHU de Montpellier - Lapeyronie",    "Montpellier",      "Occitanie",                   "34", 43.6034, 3.8637, 620_000),
    ("CH-PERPIGNAN",  "Centre Hospitalier de Perpignan",     "Perpignan",        "Occitanie",                   "66", 42.6986, 2.8954, 260_000),
    ("CHU-LYON",      "CHU de Lyon - Édouard-Herriot",       "Lyon",             "Auvergne-Rhône-Alpes",         "69", 45.7331, 4.8506, 1_400_000),
    ("CHU-GRENOBLE",  "CHU Grenoble Alpes",                  "Grenoble",         "Auvergne-Rhône-Alpes",         "38", 45.2059, 5.7397, 500_000),
    ("CHU-SAINT-ETIENNE","CHU de Saint-Étienne",             "Saint-Étienne",    "Auvergne-Rhône-Alpes",         "42", 45.4287, 4.4185, 380_000),
    ("CHU-CLERMONT",  "CHU de Clermont-Ferrand",             "Clermont-Ferrand", "Auvergne-Rhône-Alpes",         "63", 45.7772, 3.0870, 330_000),
    ("AP-HP-PITIE",   "AP-HP - Pitié-Salpêtrière",           "Paris",            "Île-de-France",               "75", 48.8388, 2.3629, 2_150_000),
    ("AP-HP-HEGP",    "AP-HP - Européen Georges-Pompidou",   "Paris",            "Île-de-France",               "75", 48.8398, 2.2725, 1_100_000),
    ("CH-VERSAILLES", "Centre Hospitalier de Versailles",    "Le Chesnay",       "Île-de-France",               "78", 48.8080, 2.1265, 460_000),
    ("CH-CRETEIL",    "CHU Henri-Mondor",                    "Créteil",          "Île-de-France",               "94", 48.7910, 2.4506, 700_000),
    ("CHU-LILLE",     "CHU de Lille",                        "Lille",            "Hauts-de-France",             "59", 50.6118, 3.0389, 1_150_000),
    ("CH-AMIENS",     "CHU Amiens-Picardie",                 "Amiens",           "Hauts-de-France",             "80", 49.8632, 2.2618, 350_000),
    ("CHU-STRASBOURG","CHU de Strasbourg - Hautepierre",     "Strasbourg",       "Grand Est",                   "67", 48.6070, 7.7098, 650_000),
    ("CHU-NANCY",     "CHU de Nancy - Brabois",              "Nancy",            "Grand Est",                   "54", 48.6693, 6.1516, 430_000),
    ("CHU-REIMS",     "CHU de Reims",                        "Reims",            "Grand Est",                   "51", 49.2493, 4.0356, 310_000),
    ("CHU-RENNES",    "CHU de Rennes - Pontchaillou",        "Rennes",           "Bretagne",                     "35", 48.1231, -1.6540, 460_000),
    ("CHU-BREST",     "CHU de Brest - Morvan",               "Brest",            "Bretagne",                     "29", 48.4023, -4.4770, 380_000),
    ("CHU-NANTES",    "CHU de Nantes - Hôtel-Dieu",          "Nantes",           "Pays de la Loire",             "44", 47.2115, -1.5497, 900_000),
    ("CHU-ANGERS",    "CHU d'Angers",                        "Angers",           "Pays de la Loire",             "49", 47.4699, -0.5219, 400_000),
    ("CHU-DIJON",     "CHU de Dijon Bourgogne",              "Dijon",            "Bourgogne-Franche-Comté",      "21", 47.3123, 5.0177, 380_000),
    ("CHU-TOURS",     "CHU de Tours - Bretonneau",           "Tours",            "Centre-Val de Loire",         "37", 47.3941, 0.6890, 350_000),
    ("CHU-CAEN",      "CHU de Caen Normandie",               "Caen",             "Normandie",                    "14", 49.1859, -0.3897, 420_000),
    ("CHU-ROUEN",     "CHU de Rouen",                        "Rouen",            "Normandie",                    "76", 49.4460, 1.0748, 560_000),
]

# Métropole uniquement : suffisant pour couvrir la France dans une carte web.
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
