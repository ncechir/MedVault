# Medvault — Portail d'accès aux données de santé

Projet 2 (Santé) — BUT Science des Données.
API de dépôt, d'instruction et de traçabilité des demandes d'accès aux
données de santé pour les études internes d'un groupe hospitalier.

## Démarrage

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Puis ouvrir **http://127.0.0.1:8000** : l'API sert elle-même l'interface, il n'y a
qu'une commande à lancer. Au premier démarrage, une base vide est peuplée
automatiquement (comptes, catalogue, patients synthétiques ; `SEED_AUTO=0` pour
l'éviter).

Repartir d'une base propre (indispensable après la mise à jour du modèle de
données, qui ne contient plus aucune identité) :

```bash
python -m app.seed --reset
```

Au premier lancement, les deux fichiers `data/cis-pathologie.csv` et
`data/ensemble_tableaux_2024.csv` doivent être présents : ils alimentent les lots
« Médicaments » et « Causes de décès ».

Pour envoyer réellement les e-mails de confirmation (sinon ils sont simulés et
consultables dans l'onglet « E-mails ») : variables `SMTP_HOTE`,
`SMTP_UTILISATEUR`, `SMTP_MOT_DE_PASSE`, `SMTP_PORT`, `SMTP_EXPEDITEUR`.

Documentation interactive : http://127.0.0.1:8000/docs

## Comptes de démonstration

| Rôle | Email | Mot de passe |
|---|---|---|
| DPO | dpo@chu-sophia.fr | DPO2026! |
| Chercheur | chercheur@chu-sophia.fr | Chercheur2026! |
| Admin | admin@chu-sophia.fr | Admin2026! |

## Données

La base contient des données patients **synthétiques** (400 patients, ~990
séjours), générées avec une graine fixe pour que les démonstrations soient
reproductibles. Aucune donnée réelle.

**La base ne contient aucune identité** : ni nom, ni prénom, ni numéro de sécurité
sociale, ni identifiant permanent (minimisation à la source, RGPD art. 5.1.c).
L'identité reste dans le dossier de soins ; une étude interne n'en a jamais besoin.
Il n'existe donc pas de « base patients » consultable : la seule vue possible sur
la population est une extraction, autorisée et limitée dans le temps.

### Jeux de données

- **Séjours hospitaliers** (`SEJOUR`) : synthétiques, sur les **27 services** d'un
  CHU (`donnees_services.py`). Tables `patient` (sexe, date de naissance, code
  postal, commune) et `sejour` (service, diagnostic, traitement, durée,
  établissement). Un lot peut viser un service précis (`service_source`) ou
  laisser le demandeur choisir parmi tous les services et, pour le territoire,
  tout ou partie des 32 établissements (`GET /lots/{id}` renvoie `services` et
  `hopitaux`).
- **Indicateurs de santé par territoire** (`INDICATEUR`) : taux d'hospitalisation,
  taux de mortalité et hospitalisations COVID-19 par établissement et par année
  (2020-2024), à la manière d'un observatoire régional de santé
  (`donnees_hopitaux.py`, inspiré de l'observatoire SIRSé PACA). Déjà agrégé :
  aucun patient concerné. Visualisable sur la carte de l'onglet « Carte ».
- **Médicaments et maladies traitées** (`MEDICAMENT`) : référentiel public fourni
  par l'utilisateur (`data/cis-pathologie.csv`, ~15 000 lignes). Aucun patient
  concerné.
- **Causes de décès en France** (`DECES`) : statistiques nationales déjà
  agrégées, 2015-2024 (`data/ensemble_tableaux_2024.csv`). Aucun patient concerné.
- **Jeux importés par le délégué** (`GENERIQUE`) : tout fichier CSV ajouté depuis
  l'onglet « Import », sous une catégorie RGPD choisie pour l'ensemble du fichier
  (`routers/import_donnees.py`). Chaque colonne devient un champ du catalogue.

Chaque `champ` indique sa colonne d'origine dans `source` et le thème d'affichage
dans `groupe`. Le seul « identifiant » proposé au chercheur est un pseudonyme
(`Identifiant du patient`), jamais une valeur en clair.

### Ce que chaque colonne donne concrètement (`protections.py`)

Le catalogue n'affiche plus les quatre catégories brutes : chaque champ porte un
libellé concret de ce qu'il renvoie par défaut (`protection`, ex. « Année
seulement », « Code anonyme », « Valeur exacte ») et si une version exacte peut
être demandée sur justification (`reductible`). C'est la même logique qui décrit
le catalogue et qui transforme réellement les données à l'extraction : il ne peut
donc pas y avoir d'écart entre ce qui est annoncé et ce qui est servi.

`GET /parametres` expose les règles de gouvernance en vigueur (délai de purge,
préavis, durée maximale) pour que l'interface les affiche sans les recopier.

### Comptes et rôles

- **Chercheur** : dépose des demandes, ne voit que les siennes, reçoit seul ses
  extractions, choisit les services et établissements concernés. Un compte se
  crée librement (`POST /auth/inscription`, adresse personnelle ou
  universitaire) ; il est toujours créé avec ce rôle. Un e-mail de confirmation
  part à chaque création de compte et à chaque connexion (`app/mailer.py`).
- **Délégué à la protection des données (DPO)** : instruit les demandes soumises
  (jamais les brouillons), décide seul de les accorder, refuser ou révoquer un
  accès, importe de nouveaux jeux de données (`/import`). Dispose d'un accès de
  supervision à toute extraction déjà autorisée (`/extractions`, journalisé
  distinctement : `EXTRACTION_CONSULTEE_DPO`), pour vérifier ce qui est
  effectivement remis — ce n'est pas un accès de recherche. Chaque décision
  d'acceptation génère une attestation PDF (tampon et signature,
  `app/attestation.py`) jointe à l'e-mail envoyé au chercheur.
- **Administrateur** : ouvre, désactive, change le rôle d'un compte ou le
  supprime définitivement (`DELETE /utilisateurs/{id}?confirmation=<email>`,
  double confirmation côté interface). N'a accès ni aux demandes, ni aux
  extractions : gérer les comptes ne donne aucun droit sur les données de
  santé. Consulte l'historique des e-mails envoyés (`/mails`).

## Protections appliquées à l'extraction

| Catégorie | Mode demandé | Ce que reçoit le chercheur |
|---|---|---|
| Identifiant direct | BRUT | refusé (règle R2, filet de sécurité dans le moteur, et option absente de l'interface) |
| Tous les services (aucun filtre) | — | autorisé, avec avertissement (règle R9 : périmètre à justifier) |
| Identifiant direct | PSEUDONYMISE | jeton HMAC-SHA256 stable, salé par demande |
| Quasi-identifiant | PSEUDONYMISE | date → année, code postal → département, âge → tranche de 10 ans, commune → masquée |
| Quasi-identifiant | BRUT | valeur exacte (soumis à la règle R5) |
| Donnée de santé | BRUT / PSEUDONYMISE | valeur exacte |
| Toute catégorie | AGREGE | exclue du détail, remplacée par des effectifs ; identifiants et quasi-identifiants comptés sous forme de jetons ou de valeurs généralisées |

Le sel dépend de l'identifiant de la demande : deux études reçoivent des
pseudonymes différents pour le même patient, ce qui interdit de fusionner deux
extractions pour reconstituer un dossier.

## Interface

`frontend/index.html` (structure) et `frontend/app.js` (logique). Aucune étape
de compilation : Tailwind et les polices sont chargés par CDN (accès internet
requis pour le style).

Mode sombre disponible depuis l'icône en haut à droite (écran de connexion et
application), mémorisé par navigateur (`localStorage`). L'onglet « Carte »
visualise les indicateurs territoriaux par établissement, sur une carte de la
France métropolitaine, avec un indicateur et une année au choix (`taux
d'hospitalisation`, `hospitalisations COVID-19`, `taux de mortalité`). Une
extraction acceptée se télécharge en CSV ou en Excel (`.xlsx`, colonnes
groupées par thème, feuille séparée pour les chiffres agrégés).

L'interface est servie par l'API sur http://127.0.0.1:8000. Elle peut aussi être
servie à part, mais jamais ouverte depuis le disque (`file://` bloque les appels) :

```bash
cd frontend && python -m http.server 3000   # vise l'API sur le port 8000
```

## Tests

```bash
pytest -q
```

## Architecture

```
app/
  config.py       seuils RGPD paramétrables
  models.py       modèle de données
  schemas.py      contrats d'entrée/sortie (Pydantic)
  security.py     hachage + JWT
  dependencies.py authentification et contrôle de rôle
  conformite.py   moteur de contrôle RGPD (R1 à R8)
  audit.py        journalisation append-only
  protections.py  ce que chaque catégorie/mode renvoie concrètement, en langage courant
  donnees_services.py  génère les séjours synthétiques sur les 27 services
  donnees_hopitaux.py  32 établissements et leurs indicateurs territoriaux synthétiques
  mailer.py       confirmations d'identité et notifications de décision (réelles ou simulées)
  attestation.py  attestation PDF d'autorisation (tampon et signature)
  excel_export.py classeur Excel d'une extraction (colonnes groupées, feuille d'effectifs)
  routers/        auth, lots, demandes, autorisations, extractions, utilisateurs,
                  parametres, journal, hopitaux, import_donnees, mails
```

## Cycle de vie d'une demande

```
BROUILLON --soumettre--> SOUMISE --instruire--> EN_INSTRUCTION
                                     |-- valider --> VALIDEE  -> Autorisation ACTIVE
                                     |-- refuser --> REFUSEE

ACTIVE --échéance--> EXPIREE --purger--> PURGEE
       --révoquer--> REVOQUEE --purger--> PURGEE
```

## Règles de conformité implémentées

| Code | Niveau | Objet | Référence |
|---|---|---|---|
| R1 | Bloquant | Demande sans aucun champ | Règle interne |
| R2 | Bloquant | Identifiant direct demandé en clair | RGPD art. 4(5), 32 |
| R3 | Bloquant | Durée absente, incohérente ou > 24 mois | RGPD art. 5.1.e |
| R4 | Bloquant | Finalité imprécise | RGPD art. 5.1.b |
| R5 | Avertissement | Croisement de quasi-identifiants | RGPD cons. 26 |
| R6 | Avertissement | Nombre de champs excessif | RGPD art. 5.1.c |
| R7 | Avertissement | Donnée de santé en clair non justifiée | RGPD art. 9 |
| R8 | Avertissement | Agrégation totale : qualité des données | AI Act art. 10 |

Une alerte bloquante empêche la soumission **et** la validation.
Le contrôle est rejoué au moment de la décision du DPO.

## Correspondance avec le backlog Jira

| Ticket | Implémentation |
|---|---|
| MED-1 | Nom du projet : Medvault |
| MED-2 | `POST /demandes` |
| MED-3 | Table `demande_champ` : champ + mode d'accès |
| MED-7 | `StatutDemande`, `GET /demandes` |
| MED-8 | Table `notification`, `POST /autorisations/taches/expiration`, `GET /autorisations/echeances` |
| MED-9 | `decision` exposée dans `DemandeOut` + notification au demandeur |
| MED-10 | `GET /demandes?statut=SOUMISE` |
| MED-11 | `CategorieChamp` + règle R2 |
| MED-12 | `POST /demandes/{id}/valider` et `/refuser`, motif obligatoire |
| MED-13 | `date_fin_acces` sur la décision |
| MED-14 | `GET /autorisations`, `GET /journal` |
| MED-15 | Règles R5 et R7 |
| MED-16 | `app/taches.py` + planificateur APScheduler dans `main.py` |
| MED-17 | `Role` + dépendance `exiger_role` |
| MED-18 | `GET /journal/export?format=csv|json`, filtrable |
| MED-19 | `GET /rapports/synthese` et `/rapports/synthese/export` |
| MED-20 | `GET /rapports/tableau-de-bord` |

Les 19 tickets des trois sprints sont couverts.

## Tâche planifiée

`POST /autorisations/taches/expiration` envoie les préavis à J-7 et clôture les
accès échus. À planifier une fois par jour (cron, ou APScheduler pour MED-16).
Elle est idempotente : deux exécutions le même jour ne produisent pas de doublon.

Le planificateur démarre avec l'application et rejoue la tâche chaque nuit à 2 h.
`PLANIFICATEUR=0` le désactive, `PLANIFICATEUR_HEURE=14` change l'horaire.

Trois étapes enchaînées :
1. préavis à J-7 aux accès arrivant à terme ;
2. clôture des accès échus ;
3. purge d'office des accès clos depuis plus de 30 jours (`DELAI_PURGE_JOURS`).
