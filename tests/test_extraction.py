"""Tests du moteur d'extraction : les protections déclarées sont-elles
réellement appliquées aux données ?"""
from datetime import date, timedelta

from app.models import Autorisation, StatutAutorisation


def demande_avec(donnees, champs, **surcharges):
    corps = {
        "lot_id": donnees["lot"].id,
        "titre_projet": "Analyse des réhospitalisations à 30 jours",
        "finalite": (
            "Mesurer le taux de réhospitalisation à 30 jours en cardiologie afin "
            "d'identifier les leviers d'amélioration du parcours de soin."
        ),
        "date_debut_souhaitee": str(date.today()),
        "date_fin_souhaitee": str(date.today() + timedelta(days=180)),
        "champs": champs,
    }
    corps.update(surcharges)
    return corps


def accorder(client, entetes, corps):
    demande_id = client.post("/demandes", json=corps,
                             headers=entetes("chercheur")).json()["id"]
    client.post(f"/demandes/{demande_id}/soumettre", headers=entetes("chercheur"))
    client.post(f"/demandes/{demande_id}/valider", headers=entetes("dpo"),
                json={"motif": "Demande proportionnée, identités pseudonymisées."})
    return demande_id


# ---------------------------------------------------------------- protections
def test_le_nom_ne_sort_jamais_en_clair(client, donnees, entetes):
    ch = donnees["champs"]
    demande_id = accorder(client, entetes, demande_avec(donnees, [
        {"champ_id": ch["nom"], "mode": "PSEUDONYMISE"},
        {"champ_id": ch["diag"], "mode": "BRUT",
         "justification": "Stratification par pathologie."},
    ]))

    e = client.get(f"/extractions/{demande_id}", headers=entetes("chercheur")).json()
    noms = [l["nom"] for l in e["lignes"]]

    assert "Durand" not in noms and "Lefebvre" not in noms
    assert all(n.startswith("PAT-") for n in noms)
    assert e["nb_lignes"] == 3  # les trois séjours de cardiologie


def test_le_pseudonyme_est_stable_par_patient(client, donnees, entetes):
    ch = donnees["champs"]
    demande_id = accorder(client, entetes, demande_avec(donnees, [
        {"champ_id": ch["nom"], "mode": "PSEUDONYMISE"},
        {"champ_id": ch["duree"], "mode": "BRUT"},
    ]))
    lignes = client.get(f"/extractions/{demande_id}",
                        headers=entetes("chercheur")).json()["lignes"]

    # Marie a deux séjours : même pseudonyme, sinon aucune analyse longitudinale
    pseudonymes = [l["nom"] for l in lignes]
    assert len(set(pseudonymes)) == 2
    assert max(pseudonymes.count(p) for p in set(pseudonymes)) == 2


def test_pseudonymes_differents_entre_deux_etudes(client, donnees, entetes):
    ch = donnees["champs"]
    champs = [{"champ_id": ch["nom"], "mode": "PSEUDONYMISE"},
              {"champ_id": ch["duree"], "mode": "BRUT"}]
    a = accorder(client, entetes, demande_avec(donnees, champs))
    b = accorder(client, entetes, demande_avec(donnees, champs))

    noms_a = {l["nom"] for l in client.get(f"/extractions/{a}",
                                           headers=entetes("chercheur")).json()["lignes"]}
    noms_b = {l["nom"] for l in client.get(f"/extractions/{b}",
                                           headers=entetes("chercheur")).json()["lignes"]}
    # Cloisonnement : impossible de fusionner deux extractions
    assert noms_a.isdisjoint(noms_b)


def test_deux_homonymes_ne_partagent_pas_le_pseudonyme(
    client, db_session, donnees, entetes
):
    """Le jeton désigne le patient, pas la chaîne « Durand »."""
    from app.models import Patient, Sejour

    sosie = Patient(ipp="IPP000003", nom="Durand", prenom="Claire",
                    num_secu="2900112345678", date_naissance=date(1990, 1, 1),
                    sexe="F", code_postal="06400", commune="Cannes")
    db_session.add(sosie)
    db_session.add(Sejour(patient=sosie, service="Cardiologie",
                          date_entree=date(2025, 5, 5), duree_sejour=3,
                          diagnostic_cim10="I10", traitements="Bêtabloquant",
                          mode_sortie="Domicile"))
    db_session.commit()

    ch = donnees["champs"]
    demande_id = accorder(client, entetes, demande_avec(donnees, [
        {"champ_id": ch["nom"], "mode": "PSEUDONYMISE"},
        {"champ_id": ch["ddn"], "mode": "PSEUDONYMISE"},
    ]))
    lignes = client.get(f"/extractions/{demande_id}",
                        headers=entetes("chercheur")).json()["lignes"]

    # Trois patients distincts, dont deux nommés Durand : trois jetons distincts
    assert len({l["nom"] for l in lignes}) == 3


def test_agrege_ne_revele_ni_nom_ni_identifiant(client, donnees, entetes):
    """Même en effectifs, un identifiant direct sort sous forme de jeton."""
    ch = donnees["champs"]
    demande_id = accorder(client, entetes, demande_avec(donnees, [
        {"champ_id": ch["nom"], "mode": "AGREGE"},
        {"champ_id": ch["duree"], "mode": "BRUT"},
    ]))
    e = client.get(f"/extractions/{demande_id}", headers=entetes("chercheur")).json()

    valeurs = [s["valeur"] for s in e["statistiques"]]
    assert valeurs and all(v.startswith("PAT-") for v in valeurs)
    assert e["identites_masquees"] is True


def test_generalisation_des_quasi_identifiants(client, donnees, entetes):
    ch = donnees["champs"]
    demande_id = accorder(client, entetes, demande_avec(donnees, [
        {"champ_id": ch["ddn"], "mode": "PSEUDONYMISE"},
        {"champ_id": ch["cp"], "mode": "PSEUDONYMISE"},
        {"champ_id": ch["duree"], "mode": "BRUT"},
    ]))
    e = client.get(f"/extractions/{demande_id}", headers=entetes("chercheur")).json()

    annees = {l["ddn"] for l in e["lignes"]}
    assert annees == {"1985", "1952"}  # jour et mois perdus

    codes = {l["cp"] for l in e["lignes"]}
    assert codes == {"06***"}  # seul le département subsiste

    transformations = {c["code"]: c["transformation"] for c in e["colonnes"]}
    assert transformations["ddn"] == "Année seulement"
    assert transformations["cp"] == "Département seulement"


def test_mode_agrege_sort_des_effectifs_pas_des_lignes(client, donnees, entetes):
    ch = donnees["champs"]
    demande_id = accorder(client, entetes, demande_avec(donnees, [
        {"champ_id": ch["duree"], "mode": "BRUT"},
        {"champ_id": ch["diag"], "mode": "AGREGE"},
    ]))
    e = client.get(f"/extractions/{demande_id}", headers=entetes("chercheur")).json()

    assert "diag" not in e["lignes"][0]
    diagnostics = {s["valeur"]: s["effectif"] for s in e["statistiques"]}
    assert diagnostics == {"I48": 1, "I10": 1, "I21": 1}


def test_donnees_de_sante_non_alterees(client, donnees, entetes):
    ch = donnees["champs"]
    demande_id = accorder(client, entetes, demande_avec(donnees, [
        {"champ_id": ch["diag"], "mode": "BRUT",
         "justification": "Stratification par pathologie."},
        {"champ_id": ch["duree"], "mode": "BRUT"},
    ]))
    lignes = client.get(f"/extractions/{demande_id}",
                        headers=entetes("chercheur")).json()["lignes"]
    assert {l["diag"] for l in lignes} == {"I48", "I10", "I21"}


# ---------------------------------------------------------------- contrôle d'accès
def test_pas_dextraction_sans_autorisation(client, donnees, entetes):
    ch = donnees["champs"]
    demande_id = client.post("/demandes", headers=entetes("chercheur"), json=demande_avec(
        donnees, [{"champ_id": ch["duree"], "mode": "BRUT"}])).json()["id"]
    r = client.get(f"/extractions/{demande_id}", headers=entetes("chercheur"))
    assert r.status_code == 403


def test_pas_dextraction_apres_revocation(client, donnees, entetes):
    ch = donnees["champs"]
    demande_id = accorder(client, entetes, demande_avec(donnees, [
        {"champ_id": ch["duree"], "mode": "BRUT"}]))
    auto_id = client.get("/autorisations", headers=entetes("dpo")).json()[0]["id"]
    client.post(f"/autorisations/{auto_id}/revoquer", headers=entetes("dpo"),
                json={"motif": "Fin anticipée du projet."})

    r = client.get(f"/extractions/{demande_id}", headers=entetes("chercheur"))
    assert r.status_code == 403
    assert "REVOQUEE" in r.json()["detail"]


def test_pas_dextraction_hors_periode(client, db_session, donnees, entetes):
    ch = donnees["champs"]
    demande_id = accorder(client, entetes, demande_avec(donnees, [
        {"champ_id": ch["duree"], "mode": "BRUT"}]))

    autorisation = db_session.query(Autorisation).filter_by(demande_id=demande_id).one()
    autorisation.date_debut = date.today() + timedelta(days=10)
    autorisation.date_fin = date.today() + timedelta(days=40)
    db_session.commit()

    r = client.get(f"/extractions/{demande_id}", headers=entetes("chercheur"))
    assert r.status_code == 403


def test_un_collegue_ne_peut_pas_extraire(client, donnees, entetes):
    ch = donnees["champs"]
    demande_id = accorder(client, entetes, demande_avec(donnees, [
        {"champ_id": ch["duree"], "mode": "BRUT"}]))
    assert client.get(f"/extractions/{demande_id}",
                      headers=entetes("chercheur2")).status_code == 404


def test_lextraction_est_journalisee(client, donnees, entetes):
    ch = donnees["champs"]
    demande_id = accorder(client, entetes, demande_avec(donnees, [
        {"champ_id": ch["duree"], "mode": "BRUT"}]))
    client.get(f"/extractions/{demande_id}", headers=entetes("chercheur"))

    entrees = client.get("/journal", headers=entetes("dpo")).json()
    consultation = next(e for e in entrees if e["action"] == "EXTRACTION_CONSULTEE")
    assert "nb_lignes" in consultation["details"]


def test_export_csv_de_lextraction(client, donnees, entetes):
    ch = donnees["champs"]
    demande_id = accorder(client, entetes, demande_avec(donnees, [
        {"champ_id": ch["nom"], "mode": "PSEUDONYMISE"},
        {"champ_id": ch["duree"], "mode": "BRUT"},
    ]))
    r = client.get(f"/extractions/{demande_id}/export", headers=entetes("chercheur"))

    assert "text/csv" in r.headers["content-type"]
    assert "Durand" not in r.text
    assert "PAT-" in r.text
