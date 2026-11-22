"""Jeu de données synthétique couvrant l'ensemble des services d'un CHU.

Module pur (aucune dépendance base de données) : il produit des dictionnaires,
que seed.py transforme en lignes. Aucune donnée réelle, aucune identité : un
patient n'est décrit que par son sexe, sa date de naissance et son lieu de vie.

Les séjours respectent des règles de bon sens (pas d'accouchement chez un
homme, pas de prostate chez une femme, pas d'enfant en gériatrie), pour que les
statistiques tirées de la base restent crédibles.
"""
from __future__ import annotations

import random
from datetime import date, timedelta

# (code postal, commune)
COMMUNES = [
    ("06000", "Nice"), ("06100", "Nice"), ("06200", "Nice"), ("06300", "Nice"),
    ("06130", "Grasse"), ("06400", "Cannes"), ("06600", "Antibes"),
    ("06800", "Cagnes-sur-Mer"), ("06560", "Valbonne"),
    ("06700", "Saint-Laurent-du-Var"), ("06110", "Le Cannet"),
    ("06500", "Menton"), ("83600", "Fréjus"), ("83700", "Saint-Raphaël"),
    ("83000", "Toulon"), ("13000", "Marseille"),
]


def d(code: str, libelle: str, poids: float = 1, sexe: str = "",
      traitements: str = "Surveillance simple") -> dict:
    """Un diagnostic : code CIM-10, libellé, fréquence relative, sexe concerné, traitements."""
    return {"code": code, "libelle": libelle, "poids": poids, "sexe": sexe,
            "traitements": traitements.split("|")}


def s(nom: str, poids: float, ages: tuple[float, float, float],
      duree: tuple[int, int], diagnostics: list[dict], sexe: str = "",
      deces: float = 2, urgences: bool = False) -> dict:
    """Un service : fréquentation, tranche d'âge (min, mode, max), durée, diagnostics."""
    return {"nom": nom, "poids": poids, "age_min": ages[0], "age_mode": ages[1],
            "age_max": ages[2], "duree_min": duree[0], "duree_max": duree[1],
            "sexe": sexe, "diagnostics": diagnostics, "deces": deces,
            "urgences": urgences}


SERVICES: list[dict] = [
    s("Urgences", 18, (0, 45, 100), (0, 2), deces=1, urgences=True, diagnostics=[
        d("R07", "Douleur thoracique", 3, "", "Antalgiques|Surveillance simple"),
        d("S82", "Fracture de la jambe", 2, "", "Immobilisation|Antalgiques"),
        d("R50", "Fièvre", 3, "", "Antibiotique|Surveillance simple"),
        d("R06", "Difficulté respiratoire", 2, "", "Oxygénothérapie|Bronchodilatateur"),
        d("R55", "Malaise ou syncope", 2, "", "Perfusion|Surveillance simple"),
        d("R10", "Douleur abdominale", 3, "", "Antalgiques|Perfusion"),
        d("S61", "Plaie de la main", 2, "", "Suture|Antalgiques"),
        d("R51", "Maux de tête", 2, "", "Antalgiques"),
        d("R11", "Vomissements", 1, "", "Réhydratation|Perfusion"),
    ]),
    s("Cardiologie", 10, (18, 68, 100), (2, 10), deces=3, diagnostics=[
        d("I21", "Infarctus aigu du myocarde", 3, "", "Angioplastie + stent|Statine + aspirine"),
        d("I50", "Insuffisance cardiaque", 4, "", "Diurétique de l'anse|Inhibiteur de l'enzyme de conversion"),
        d("I48", "Fibrillation auriculaire", 3, "", "Anticoagulant oral|Bêtabloquant"),
        d("I10", "Hypertension essentielle", 3, "", "Inhibiteur de l'enzyme de conversion|Bêtabloquant"),
        d("I25", "Cardiopathie ischémique chronique", 2, "", "Statine + aspirine|Angioplastie + stent"),
        d("I34", "Atteinte de la valve mitrale", 1, "", "Chirurgie valvulaire|Surveillance simple"),
        d("I20", "Angine de poitrine", 2, "", "Bêtabloquant|Statine + aspirine"),
    ]),
    s("Pneumologie", 6, (18, 66, 100), (3, 12), deces=4, diagnostics=[
        d("J44", "Bronchopneumopathie chronique obstructive", 4, "", "Bronchodilatateur|Oxygénothérapie"),
        d("J18", "Pneumonie", 3, "", "Antibiotique|Oxygénothérapie"),
        d("J45", "Asthme", 2, "", "Bronchodilatateur|Corticothérapie"),
        d("J96", "Insuffisance respiratoire", 2, "", "Ventilation non invasive|Oxygénothérapie"),
        d("I26", "Embolie pulmonaire", 2, "", "Anticoagulant"),
        d("C34", "Tumeur maligne du poumon", 2, "", "Chimiothérapie|Immunothérapie"),
        d("J84", "Pneumopathie interstitielle", 1, "", "Corticothérapie"),
    ]),
    s("Neurologie", 5, (18, 62, 100), (3, 12), deces=3, diagnostics=[
        d("I63", "Infarctus cérébral", 4, "", "Thrombolyse|Antiagrégant"),
        d("G40", "Épilepsie", 2, "", "Antiépileptique"),
        d("G20", "Maladie de Parkinson", 2, "", "Traitement dopaminergique|Rééducation"),
        d("G35", "Sclérose en plaques", 2, "", "Immunomodulateur|Corticothérapie"),
        d("G43", "Migraine", 1, "", "Antalgiques|Traitement de fond"),
        d("G45", "Accident ischémique transitoire", 2, "", "Antiagrégant|Anticoagulant"),
        d("G30", "Maladie d'Alzheimer", 1, "", "Adaptation thérapeutique"),
    ]),
    s("Gastro-entérologie", 5, (18, 58, 100), (2, 9), deces=2, diagnostics=[
        d("K29", "Gastrite", 2, "", "Inhibiteur de la pompe à protons"),
        d("K50", "Maladie de Crohn", 2, "", "Immunosuppresseur|Corticothérapie"),
        d("K51", "Rectocolite hémorragique", 2, "", "Immunosuppresseur|Corticothérapie"),
        d("K74", "Cirrhose du foie", 3, "", "Diurétique de l'anse|Nutrition entérale"),
        d("K85", "Pancréatite aiguë", 2, "", "Perfusion|Antalgiques"),
        d("K25", "Ulcère de l'estomac", 2, "", "Inhibiteur de la pompe à protons|Endoscopie thérapeutique"),
        d("K92", "Hémorragie digestive", 2, "", "Endoscopie thérapeutique|Transfusion"),
    ]),
    s("Endocrinologie-diabétologie", 4, (18, 56, 95), (2, 8), deces=1, diagnostics=[
        d("E11", "Diabète de type 2", 5, "", "Metformine|Insuline"),
        d("E10", "Diabète de type 1", 3, "", "Insuline|Éducation thérapeutique"),
        d("E05", "Hyperthyroïdie", 1, "", "Antithyroïdien"),
        d("E03", "Hypothyroïdie", 1, "", "Lévothyroxine"),
        d("E66", "Obésité", 2, "", "Éducation thérapeutique|Chirurgie bariatrique"),
        d("E78", "Excès de lipides dans le sang", 1, "", "Statine"),
    ]),
    s("Néphrologie", 3, (18, 66, 100), (2, 10), deces=4, diagnostics=[
        d("N18", "Insuffisance rénale chronique", 4, "", "Hémodialyse|Diurétique de l'anse"),
        d("N17", "Insuffisance rénale aiguë", 3, "", "Perfusion|Hémodialyse"),
        d("N04", "Syndrome néphrotique", 1, "", "Corticothérapie|Immunosuppresseur"),
        d("N20", "Calcul du rein", 1, "", "Antalgiques|Lithotripsie"),
        d("N10", "Infection du rein", 2, "", "Antibiotique"),
    ]),
    s("Hématologie", 3, (18, 60, 100), (3, 14), deces=5, diagnostics=[
        d("D50", "Anémie par manque de fer", 2, "", "Fer par voie veineuse|Transfusion"),
        d("C91", "Leucémie lymphoïde", 2, "", "Chimiothérapie|Immunothérapie"),
        d("C92", "Leucémie myéloïde", 2, "", "Chimiothérapie|Greffe de cellules souches"),
        d("D57", "Drépanocytose", 1, "", "Transfusion|Antalgiques"),
        d("D69", "Purpura et troubles de la coagulation", 1, "", "Corticothérapie"),
        d("C85", "Lymphome non hodgkinien", 2, "", "Chimiothérapie|Immunothérapie"),
    ]),
    s("Oncologie", 6, (25, 65, 100), (1, 9), deces=5, diagnostics=[
        d("C50", "Tumeur maligne du sein", 4, "F", "Chimiothérapie|Hormonothérapie|Radiothérapie"),
        d("C61", "Tumeur maligne de la prostate", 3, "M", "Hormonothérapie|Radiothérapie"),
        d("C18", "Tumeur maligne du côlon", 3, "", "Chimiothérapie|Immunothérapie"),
        d("C34", "Tumeur maligne du poumon", 3, "", "Chimiothérapie|Immunothérapie"),
        d("C25", "Tumeur maligne du pancréas", 2, "", "Chimiothérapie|Soins de support"),
        d("C43", "Mélanome malin de la peau", 1, "", "Immunothérapie"),
        d("C56", "Tumeur maligne de l'ovaire", 1, "F", "Chimiothérapie"),
    ]),
    s("Rhumatologie", 3, (18, 60, 100), (2, 8), deces=1, diagnostics=[
        d("M05", "Polyarthrite rhumatoïde", 3, "", "Méthotrexate|Biothérapie"),
        d("M81", "Ostéoporose", 2, "", "Traitement de l'ostéoporose"),
        d("M10", "Goutte", 1, "", "Anti-inflammatoire"),
        d("M54", "Douleur du dos", 3, "", "Anti-inflammatoire|Infiltration"),
        d("M32", "Lupus érythémateux systémique", 1, "", "Corticothérapie|Biothérapie"),
        d("M45", "Spondylarthrite ankylosante", 1, "", "Biothérapie|Anti-inflammatoire"),
    ]),
    s("Dermatologie", 2, (2, 45, 100), (1, 6), deces=0.5, diagnostics=[
        d("L40", "Psoriasis", 3, "", "Dermocorticoïde|Photothérapie|Biothérapie"),
        d("L20", "Dermatite atopique", 3, "", "Dermocorticoïde"),
        d("L03", "Infection de la peau", 2, "", "Antibiotique"),
        d("L50", "Urticaire", 1, "", "Antihistaminique"),
        d("L10", "Pemphigus", 1, "", "Corticothérapie|Immunosuppresseur"),
        d("L97", "Ulcère de jambe", 2, "", "Pansements|Antibiotique"),
    ]),
    s("Maladies infectieuses", 3, (15, 50, 100), (3, 14), deces=3, diagnostics=[
        d("A41", "Septicémie", 3, "", "Antibiotique par voie veineuse"),
        d("J18", "Pneumonie", 2, "", "Antibiotique par voie veineuse|Oxygénothérapie"),
        d("B20", "Infection par le VIH", 2, "", "Antirétroviral"),
        d("A46", "Érysipèle", 2, "", "Antibiotique"),
        d("B18", "Hépatite virale chronique", 1, "", "Antiviral"),
        d("A15", "Tuberculose respiratoire", 1, "", "Antituberculeux|Isolement"),
        d("U07", "COVID-19", 2, "", "Antiviral|Oxygénothérapie"),
    ]),
    s("Médecine interne", 5, (18, 68, 105), (3, 14), deces=4, diagnostics=[
        d("R50", "Fièvre prolongée", 2, "", "Bilan diagnostique|Antibiotique"),
        d("D86", "Sarcoïdose", 1, "", "Corticothérapie"),
        d("E86", "Déshydratation", 2, "", "Perfusion"),
        d("D50", "Anémie par manque de fer", 1, "", "Fer par voie veineuse"),
        d("N39", "Infection urinaire", 3, "", "Antibiotique"),
        d("M31", "Vascularite", 1, "", "Corticothérapie|Immunosuppresseur"),
        d("I50", "Insuffisance cardiaque", 2, "", "Diurétique de l'anse"),
    ]),
    s("Gériatrie", 6, (75, 86, 105), (5, 21), deces=6, diagnostics=[
        d("S72", "Fracture du col du fémur", 3, "", "Prothèse de hanche|Rééducation"),
        d("F03", "Démence", 2, "", "Adaptation thérapeutique"),
        d("I50", "Insuffisance cardiaque", 3, "", "Diurétique de l'anse"),
        d("N39", "Infection urinaire", 3, "", "Antibiotique"),
        d("R29", "Chutes à répétition", 2, "", "Kinésithérapie|Adaptation thérapeutique"),
        d("E86", "Déshydratation", 2, "", "Perfusion"),
    ]),
    s("Psychiatrie", 5, (16, 40, 90), (5, 40), deces=0.5, diagnostics=[
        d("F32", "Épisode dépressif", 4, "", "Antidépresseur|Psychothérapie"),
        d("F20", "Schizophrénie", 3, "", "Antipsychotique"),
        d("F31", "Trouble bipolaire", 2, "", "Thymorégulateur|Antipsychotique"),
        d("F41", "Trouble anxieux", 2, "", "Anxiolytique|Psychothérapie"),
        d("F10", "Troubles liés à l'alcool", 2, "", "Sevrage encadré|Psychothérapie"),
        d("F60", "Trouble de la personnalité", 1, "", "Psychothérapie"),
    ]),
    s("Pédiatrie", 7, (0, 4, 17), (1, 7), deces=0.2, diagnostics=[
        d("J21", "Bronchiolite aiguë", 4, "", "Oxygénothérapie|Surveillance simple"),
        d("A08", "Gastro-entérite", 3, "", "Réhydratation"),
        d("J03", "Angine", 2, "", "Antibiotique"),
        d("N39", "Infection urinaire", 1, "", "Antibiotique"),
        d("E10", "Diabète de type 1", 1, "", "Insuline|Éducation thérapeutique"),
        d("J45", "Asthme", 2, "", "Bronchodilatateur|Corticothérapie"),
        d("K35", "Appendicite aiguë", 2, "", "Appendicectomie|Antibiotique"),
    ]),
    s("Néonatologie", 2, (0, 0.01, 0.06), (3, 30), deces=1, diagnostics=[
        d("P07", "Prématurité", 4, "", "Incubateur|Nutrition parentérale"),
        d("P22", "Détresse respiratoire du nouveau-né", 3, "", "Ventilation assistée|Oxygénothérapie"),
        d("P59", "Ictère du nouveau-né", 3, "", "Photothérapie"),
        d("P36", "Infection du nouveau-né", 2, "", "Antibiotique"),
        d("P92", "Difficulté d'alimentation du nouveau-né", 2, "", "Nutrition parentérale"),
    ]),
    s("Gynécologie-obstétrique", 7, (16, 30, 50), (2, 6), sexe="F", deces=0.1, diagnostics=[
        d("O80", "Accouchement spontané", 6, "", "Analgésie péridurale|Surveillance obstétricale"),
        d("O82", "Accouchement par césarienne", 3, "", "Césarienne|Antalgiques"),
        d("O14", "Pré-éclampsie", 1, "", "Surveillance obstétricale|Antihypertenseur"),
        d("O24", "Diabète gestationnel", 1, "", "Insuline|Éducation thérapeutique"),
        d("N80", "Endométriose", 1, "", "Chirurgie gynécologique"),
        d("D25", "Fibrome de l'utérus", 1, "", "Chirurgie gynécologique"),
        d("O03", "Fausse couche", 1, "", "Curetage|Surveillance simple"),
    ]),
    s("Chirurgie orthopédique", 7, (10, 62, 100), (2, 9), deces=1, diagnostics=[
        d("S72", "Fracture du col du fémur", 2, "", "Prothèse de hanche|Ostéosynthèse"),
        d("M17", "Arthrose du genou", 3, "", "Prothèse de genou|Rééducation"),
        d("M16", "Arthrose de la hanche", 3, "", "Prothèse de hanche|Rééducation"),
        d("S82", "Fracture de la jambe", 2, "", "Ostéosynthèse|Immobilisation"),
        d("S52", "Fracture de l'avant-bras", 2, "", "Ostéosynthèse|Immobilisation"),
        d("M51", "Hernie discale", 1, "", "Chirurgie du rachis|Antalgiques"),
    ]),
    s("Chirurgie digestive", 5, (16, 58, 100), (2, 12), deces=2, diagnostics=[
        d("K35", "Appendicite aiguë", 3, "", "Appendicectomie|Antibiotique"),
        d("K80", "Calculs de la vésicule biliaire", 3, "", "Cholécystectomie"),
        d("K40", "Hernie de l'aine", 2, "", "Cure de hernie"),
        d("C18", "Tumeur maligne du côlon", 2, "", "Colectomie|Chimiothérapie"),
        d("K56", "Occlusion intestinale", 2, "", "Chirurgie digestive urgente|Perfusion"),
        d("K57", "Diverticulose du côlon", 1, "", "Antibiotique|Colectomie"),
    ]),
    s("Chirurgie vasculaire", 3, (40, 70, 100), (2, 10), deces=3, diagnostics=[
        d("I70", "Athérosclérose des artères", 3, "", "Pontage|Angioplastie"),
        d("I71", "Anévrisme de l'aorte", 2, "", "Endoprothèse aortique"),
        d("I83", "Varices des jambes", 2, "", "Stripping veineux"),
        d("I74", "Obstruction d'une artère", 2, "", "Pontage|Anticoagulant"),
        d("I80", "Phlébite", 1, "", "Anticoagulant"),
    ]),
    s("Urologie", 4, (18, 65, 100), (1, 7), deces=1, diagnostics=[
        d("N40", "Hypertrophie bénigne de la prostate", 3, "M", "Résection endoscopique"),
        d("N20", "Calcul urinaire", 3, "", "Lithotripsie|Antalgiques"),
        d("C67", "Tumeur maligne de la vessie", 2, "", "Chirurgie oncologique|Chimiothérapie"),
        d("N39", "Infection urinaire", 2, "", "Antibiotique"),
        d("C61", "Tumeur maligne de la prostate", 2, "M", "Chirurgie oncologique|Radiothérapie"),
        d("N13", "Obstruction des voies urinaires", 1, "", "Sonde vésicale"),
    ]),
    s("ORL", 3, (3, 40, 100), (0, 4), deces=0.2, diagnostics=[
        d("J35", "Hypertrophie des amygdales", 3, "", "Amygdalectomie"),
        d("J32", "Sinusite chronique", 2, "", "Chirurgie des sinus|Corticothérapie"),
        d("H66", "Otite moyenne", 2, "", "Pose d'aérateurs transtympaniques|Antibiotique"),
        d("J34", "Déviation de la cloison nasale", 1, "", "Chirurgie du nez"),
        d("C32", "Tumeur maligne du larynx", 1, "", "Chirurgie oncologique|Radiothérapie"),
    ]),
    s("Ophtalmologie", 3, (2, 70, 100), (0, 2), deces=0.1, diagnostics=[
        d("H25", "Cataracte", 6, "", "Chirurgie de la cataracte"),
        d("H40", "Glaucome", 2, "", "Collyre hypotonisant|Laser"),
        d("H35", "Dégénérescence de la rétine", 2, "", "Injection intravitréenne"),
        d("H33", "Décollement de la rétine", 1, "", "Chirurgie rétinienne|Laser"),
        d("H10", "Conjonctivite", 1, "", "Collyre antibiotique"),
    ]),
    s("Réanimation", 3, (18, 62, 100), (2, 25), deces=22, diagnostics=[
        d("J96", "Insuffisance respiratoire aiguë", 3, "", "Ventilation mécanique|Sédation"),
        d("A41", "Septicémie", 3, "", "Antibiotique par voie veineuse|Catécholamines"),
        d("I46", "Arrêt cardiaque", 2, "", "Ventilation mécanique|Catécholamines"),
        d("R57", "Choc", 2, "", "Catécholamines|Épuration extra-rénale"),
        d("J80", "Détresse respiratoire aiguë de l'adulte", 1, "", "Ventilation mécanique|Sédation"),
        d("T07", "Polytraumatisme", 1, "", "Ventilation mécanique|Transfusion"),
    ]),
    s("Soins palliatifs", 1.5, (40, 75, 105), (5, 30), deces=45, diagnostics=[
        d("C25", "Tumeur maligne du pancréas", 2, "", "Antalgiques de palier 3|Soins de confort"),
        d("C34", "Tumeur maligne du poumon", 2, "", "Antalgiques de palier 3|Soins de confort"),
        d("C50", "Tumeur maligne du sein", 1, "F", "Antalgiques de palier 3|Soins de confort"),
        d("C61", "Tumeur maligne de la prostate", 1, "M", "Antalgiques de palier 3|Soins de confort"),
        d("Z51", "Soins palliatifs", 2, "", "Sédation palliative|Accompagnement psychologique"),
    ]),
    s("Médecine physique et réadaptation", 3, (16, 62, 100), (10, 45), deces=0.5, diagnostics=[
        d("I69", "Séquelles d'accident vasculaire cérébral", 3, "", "Rééducation motrice|Orthophonie"),
        d("G82", "Paraplégie ou tétraplégie", 1, "", "Rééducation motrice|Appareillage"),
        d("S72", "Fracture du col du fémur", 2, "", "Rééducation motrice|Ergothérapie"),
        d("M17", "Arthrose du genou", 1, "", "Rééducation motrice"),
        d("Z50", "Soins de rééducation", 2, "", "Rééducation motrice|Ergothérapie"),
    ]),
]

NOMS_SERVICES = [x["nom"] for x in SERVICES]

MOTIFS_URGENCES = {
    "R07": "Douleur thoracique", "S82": "Traumatisme du membre inférieur",
    "R50": "Fièvre", "R06": "Difficulté respiratoire", "R55": "Malaise",
    "R10": "Douleur abdominale", "S61": "Plaie", "R51": "Maux de tête",
    "R11": "Vomissements",
}

# Résultat d'examen (biologie ou imagerie) à l'origine du diagnostic : de quoi
# permettre une vraie analyse, au-delà du seul libellé de la maladie.
# (type d'examen, modèle de compte-rendu ; {v} est remplacé par une valeur tirée au hasard)
RESULTATS_ANALYSE: dict[str, tuple[str, str]] = {
    "I21": ("Biologie", "Troponine I ultrasensible : {v} ng/L (normale < 14)"),
    "I50": ("Biologie", "NT-proBNP : {v} pg/mL (normale < 125)"),
    "I48": ("Imagerie", "ECG : fibrillation auriculaire, fréquence ventriculaire à {v} / min"),
    "I10": ("Biologie", "Pression artérielle mesurée : {v}/95 mmHg"),
    "I25": ("Imagerie", "Coronarographie : sténose estimée à {v} % sur l'artère interventriculaire antérieure"),
    "I20": ("Imagerie", "Épreuve d'effort : sous-décalage ST à {v} % de la fréquence maximale théorique"),
    "J44": ("Biologie", "Spirométrie : VEMS à {v} % de la valeur prédite"),
    "J18": ("Imagerie", "Radiographie thoracique : foyer de condensation du lobe, CRP à {v} mg/L"),
    "J45": ("Biologie", "Spirométrie : réversibilité du VEMS de {v} % après bronchodilatateur"),
    "I26": ("Imagerie", "Angioscanner thoracique : embolie pulmonaire segmentaire, D-dimères à {v} µg/L"),
    "C34": ("Imagerie", "Scanner thoracique : masse pulmonaire de {v} mm, biopsie en cours"),
    "I63": ("Imagerie", "IRM cérébrale : zone d'ischémie récente, territoire sylvien, à {v} mm"),
    "G40": ("Imagerie", "Électroencéphalogramme : anomalies paroxystiques intercritiques"),
    "G20": ("Imagerie", "DatScan : hypofixation striatale de {v} %"),
    "K74": ("Biologie", "Bilan hépatique : ASAT à {v} UI/L, albumine abaissée"),
    "K25": ("Imagerie", "Endoscopie digestive haute : ulcère gastrique de {v} mm"),
    "K92": ("Biologie", "Hémoglobine : {v} g/dL (normale 12-16), nécessitant transfusion"),
    "E11": ("Biologie", "Hémoglobine glyquée (HbA1c) : {v} % (normale < 6)"),
    "E10": ("Biologie", "Glycémie à jeun : {v} mmol/L (normale 3,9-5,5)"),
    "E05": ("Biologie", "TSH : {v} mUI/L (normale 0,4-4), T4 libre élevée"),
    "N18": ("Biologie", "Débit de filtration glomérulaire (DFG) : {v} mL/min/1,73 m²"),
    "N17": ("Biologie", "Créatininémie : {v} µmol/L, en forte hausse sur 48 heures"),
    "N20": ("Imagerie", "Scanner abdominal sans injection : calcul urinaire de {v} mm"),
    "D50": ("Biologie", "Hémoglobine : {v} g/dL (normale 12-16), ferritine basse"),
    "C91": ("Biologie", "Numération formule sanguine : {v} % de lymphoblastes circulants"),
    "C50": ("Imagerie", "Mammographie : masse spiculée de {v} mm, classée ACR 5"),
    "C61": ("Biologie", "PSA total : {v} ng/mL (normale < 4)"),
    "C18": ("Imagerie", "Coloscopie : lésion bourgeonnante du côlon, biopsie en cours"),
    "M05": ("Biologie", "Facteur rhumatoïde positif, anti-CCP à {v} UI/mL"),
    "M81": ("Imagerie", "Ostéodensitométrie : T-score à -{v}"),
    "L40": ("Imagerie", "Score PASI (sévérité du psoriasis) : {v} / 72"),
    "A41": ("Biologie", "Hémocultures positives, procalcitonine à {v} ng/mL"),
    "B20": ("Biologie", "Charge virale VIH : {v} copies/mL"),
    "U07": ("Biologie", "PCR SARS-CoV-2 : positive, seuil de détection Ct à {v}"),
    "S72": ("Imagerie", "Radiographie du bassin : fracture déplacée du col fémoral, angle à {v}°"),
    "H25": ("Imagerie", "Examen ophtalmologique : acuité visuelle réduite à {v}/10"),
    "F32": ("Biologie", "Échelle de dépression (score MADRS) : {v} / 60"),
    "O14": ("Biologie", "Protéinurie des 24 heures : {v} g/24h"),
}


def resultat_analyse(alea: random.Random, code: str, libelle: str) -> str:
    """Compte-rendu d'un examen plausible à l'origine du diagnostic."""
    type_examen, modele = RESULTATS_ANALYSE.get(code, (
        "Biologie",
        f"Examen complémentaire en lien avec « {libelle.lower()} » : résultat hors des normes "
        f"usuelles, cohérent avec le diagnostic retenu.",
    ))
    valeur = round(alea.uniform(1.2, 94.8), 1)
    return f"{type_examen} — " + (modele.format(v=valeur) if "{v}" in modele else modele)


def _age_en_annees(naissance: date, reference: date) -> float:
    return (reference - naissance).days / 365.25


def _tirer(alea: random.Random, elements: list, cle: str = "poids"):
    return alea.choices(elements, weights=[e[cle] for e in elements])[0]


def _nouveau_patient(alea: random.Random, service: dict, entree: date) -> dict:
    age = alea.triangular(service["age_min"], service["age_max"], service["age_mode"])
    code_postal, commune = alea.choice(COMMUNES)
    return {
        "date_naissance": entree - timedelta(days=int(age * 365.25)),
        "sexe": service["sexe"] or alea.choice("FM"),
        "code_postal": code_postal,
        "commune": commune,
    }


def _compatible(patient: dict, service: dict, entree: date) -> bool:
    if service["sexe"] and patient["sexe"] != service["sexe"]:
        return False
    return service["age_min"] <= _age_en_annees(patient["date_naissance"], entree) <= service["age_max"]


def _sejour(alea: random.Random, service: dict, patient: dict, entree: date) -> dict:
    candidats = [x for x in service["diagnostics"]
                 if not x["sexe"] or x["sexe"] == patient["sexe"]]
    diagnostic = _tirer(alea, candidats)
    duree = int(alea.triangular(service["duree_min"], service["duree_max"],
                                service["duree_min"] + (service["duree_max"] - service["duree_min"]) * 0.3))
    poids_sortie = [70, 12, 10, 5, service["deces"]]
    mode_sortie = alea.choices(
        ["Retour à domicile",
         "Transfert vers un service de convalescence (soins de suite)",
         "Mutation dans un autre service de l'hôpital",
         "Départ contre l'avis des médecins",
         "Décès durant le séjour"],
        weights=poids_sortie)[0]
    ligne = {
        "service": service["nom"], "date_entree": entree, "duree_sejour": duree,
        "diagnostic_cim10": diagnostic["code"],
        "diagnostic_libelle": diagnostic["libelle"],
        "traitements": alea.choice(diagnostic["traitements"]),
        "mode_sortie": mode_sortie,
        "resultat_analyse": resultat_analyse(alea, diagnostic["code"], diagnostic["libelle"]),
        "motif_admission": "", "gravite_ccmu": 0, "attente_minutes": 0,
    }
    if service["urgences"]:
        ligne["motif_admission"] = MOTIFS_URGENCES.get(diagnostic["code"], diagnostic["libelle"])
        ligne["gravite_ccmu"] = alea.choices([1, 2, 3, 4, 5], weights=[20, 40, 27, 10, 3])[0]
        ligne["attente_minutes"] = int(alea.triangular(10, 420, 60))
    return ligne


def generer(alea: random.Random, nb_sejours: int, aujourdhui: date,
            part_reprises: float = 0.35) -> tuple[list[dict], list[dict]]:
    """Renvoie (patients, séjours). Chaque séjour porte l'indice de son patient."""
    patients: list[dict] = []
    sejours: list[dict] = []
    for _ in range(nb_sejours):
        service = _tirer(alea, SERVICES)
        entree = aujourdhui - timedelta(days=alea.randint(1, 1800))

        patient = None
        if patients and alea.random() < part_reprises:
            for _essai in range(25):
                candidat = alea.choice(patients)
                if _compatible(candidat, service, entree):
                    patient = candidat
                    break
        if patient is None:
            patient = _nouveau_patient(alea, service, entree)
            patient["indice"] = len(patients)
            patients.append(patient)

        ligne = _sejour(alea, service, patient, entree)
        ligne["patient_indice"] = patient["indice"]
        sejours.append(ligne)
    return patients, sejours
