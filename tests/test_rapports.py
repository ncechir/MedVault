"""Tests des tickets MED-16 (purge automatique), MED-18 (export du journal),
MED-19 (synthèse) et MED-20 (tableau de bord)."""
from datetime import date, timedelta

from app.config import DELAI_PURGE_JOURS
from app.models import Autorisation, StatutAutorisation


def parcours_valide(client, entetes, corps):
    """Dépose, soumet et fait valider une demande. Renvoie son identifiant."""
    demande_id = client.post("/demandes", json=corps,
                             headers=entetes("chercheur")).json()["id"]
    client.post(f"/demandes/{demande_id}/soumettre", headers=entetes("chercheur"))
    client.post(f"/demandes/{demande_id}/valider", headers=entetes("dpo"),
                json={"motif": "Validation conforme aux règles de gouvernance."})
    return demande_id


def deplacer_echeance(db_session, demande_id, jours):
    autorisation = db_session.query(Autorisation).filter_by(demande_id=demande_id).one()
    autorisation.date_debut = date.today() + timedelta(days=jours - 30)
    autorisation.date_fin = date.today() + timedelta(days=jours)
    db_session.commit()
    return autorisation


# ---------------------------------------------------------------- MED-16
def test_purge_automatique_apres_le_delai(
    client, db_session, donnees, entetes, demande_valide
):
    demande_id = parcours_valide(client, entetes, demande_valide)
    deplacer_echeance(db_session, demande_id, -(DELAI_PURGE_JOURS + 5))

    resume = client.post("/autorisations/taches/expiration",
                         headers=entetes("dpo")).json()
    assert len(resume["acces_clotures"]) == 1
    assert resume["donnees_purgees"] == 1

    autorisation = client.get("/autorisations", headers=entetes("dpo")).json()[0]
    assert autorisation["statut"] == "PURGEE"
    assert autorisation["purge_effectuee_le"] is not None


def test_pas_de_purge_avant_le_delai(
    client, db_session, donnees, entetes, demande_valide
):
    demande_id = parcours_valide(client, entetes, demande_valide)
    deplacer_echeance(db_session, demande_id, -2)

    resume = client.post("/autorisations/taches/expiration",
                         headers=entetes("dpo")).json()
    assert resume["donnees_purgees"] == 0
    assert client.get("/autorisations",
                      headers=entetes("dpo")).json()[0]["statut"] == "EXPIREE"


def test_la_purge_automatique_est_tracee(
    client, db_session, donnees, entetes, demande_valide
):
    demande_id = parcours_valide(client, entetes, demande_valide)
    deplacer_echeance(db_session, demande_id, -(DELAI_PURGE_JOURS + 5))
    client.post("/autorisations/taches/expiration", headers=entetes("dpo"))

    actions = {e["action"] for e in
               client.get("/journal", headers=entetes("dpo")).json()}
    assert "PURGE_AUTOMATIQUE" in actions


# ---------------------------------------------------------------- MED-18
def test_export_csv_du_journal(client, donnees, entetes, demande_valide):
    parcours_valide(client, entetes, demande_valide)
    r = client.get("/journal/export?format=csv", headers=entetes("dpo"))
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    assert "attachment" in r.headers["content-disposition"]

    lignes = r.text.strip().splitlines()
    assert lignes[0].lstrip("\ufeff").startswith("id;horodatage")
    assert any("DEMANDE_VALIDEE" in l for l in lignes)


def test_export_json_du_journal(client, donnees, entetes, demande_valide):
    parcours_valide(client, entetes, demande_valide)
    r = client.get("/journal/export?format=json", headers=entetes("dpo"))
    entrees = r.json()
    assert isinstance(entrees, list)
    assert {"action", "horodatage", "utilisateur_email"} <= set(entrees[0])


def test_export_filtre_par_action(client, donnees, entetes, demande_valide):
    parcours_valide(client, entetes, demande_valide)
    entrees = client.get("/journal/export?format=json&action=DEMANDE_VALIDEE",
                         headers=entetes("dpo")).json()
    assert entrees and all(e["action"] == "DEMANDE_VALIDEE" for e in entrees)


def test_lexport_est_lui_meme_journalise(client, donnees, entetes, demande_valide):
    parcours_valide(client, entetes, demande_valide)
    client.get("/journal/export", headers=entetes("dpo"))
    actions = {e["action"] for e in
               client.get("/journal", headers=entetes("dpo")).json()}
    assert "JOURNAL_EXPORTE" in actions


def test_export_interdit_au_chercheur(client, donnees, entetes):
    assert client.get("/journal/export", headers=entetes("chercheur")).status_code == 403


def test_liste_des_actions_disponibles(client, donnees, entetes, demande_valide):
    parcours_valide(client, entetes, demande_valide)
    actions = client.get("/journal/actions", headers=entetes("dpo")).json()
    assert "DEMANDE_SOUMISE" in actions
    assert actions == sorted(actions)


# ---------------------------------------------------------------- MED-19
def test_synthese_sur_la_periode(client, donnees, entetes, demande_valide):
    parcours_valide(client, entetes, demande_valide)
    s = client.get("/rapports/synthese", headers=entetes("dpo")).json()

    assert s["demandes_deposees"] == 1
    assert s["demandes_validees"] == 1
    assert s["demandes_refusees"] == 0
    assert s["taux_de_refus"] == 0.0
    assert s["delai_moyen_instruction_jours"] is not None
    assert s["duree_moyenne_acces_jours"] == 180


def test_synthese_compte_les_refus(client, donnees, entetes, demande_valide):
    demande_id = client.post("/demandes", json=demande_valide,
                             headers=entetes("chercheur")).json()["id"]
    client.post(f"/demandes/{demande_id}/soumettre", headers=entetes("chercheur"))
    client.post(f"/demandes/{demande_id}/refuser", headers=entetes("dpo"),
                json={"motif": "Finalité déjà couverte par une étude en cours."})

    s = client.get("/rapports/synthese", headers=entetes("dpo")).json()
    assert s["demandes_refusees"] == 1
    assert s["taux_de_refus"] == 100.0


def test_synthese_repartit_les_colonnes(client, donnees, entetes, demande_valide):
    parcours_valide(client, entetes, demande_valide)
    s = client.get("/rapports/synthese", headers=entetes("dpo")).json()

    modes = {l["libelle"]: l["valeur"] for l in s["colonnes_par_mode"]}
    assert modes["PSEUDONYMISE"] == 1
    assert modes["BRUT"] == 2

    categories = {l["libelle"]: l["valeur"] for l in s["colonnes_par_categorie"]}
    assert categories["IDENTIFIANT_DIRECT"] == 1


def test_synthese_hors_periode_est_vide(client, donnees, entetes, demande_valide):
    parcours_valide(client, entetes, demande_valide)
    s = client.get("/rapports/synthese?debut=2020-01-01&fin=2020-12-31",
                   headers=entetes("dpo")).json()
    assert s["demandes_deposees"] == 0
    assert s["taux_de_refus"] == 0.0


def test_export_csv_de_la_synthese(client, donnees, entetes, demande_valide):
    parcours_valide(client, entetes, demande_valide)
    r = client.get("/rapports/synthese/export", headers=entetes("dpo"))
    assert "text/csv" in r.headers["content-type"]
    assert "Demandes validées" in r.text


def test_synthese_interdite_au_chercheur(client, donnees, entetes):
    assert client.get("/rapports/synthese",
                      headers=entetes("chercheur")).status_code == 403


# ---------------------------------------------------------------- MED-20
def test_tableau_de_bord_en_attente(client, donnees, entetes, demande_valide):
    demande_id = client.post("/demandes", json=demande_valide,
                             headers=entetes("chercheur")).json()["id"]
    client.post(f"/demandes/{demande_id}/soumettre", headers=entetes("chercheur"))

    t = client.get("/rapports/tableau-de-bord", headers=entetes("dpo")).json()
    assert t["a_instruire"] == 1
    assert t["acces_actifs"] == 0


def test_tableau_de_bord_signale_les_echeances(
    client, db_session, donnees, entetes, demande_valide
):
    demande_id = parcours_valide(client, entetes, demande_valide)
    deplacer_echeance(db_session, demande_id, 3)

    t = client.get("/rapports/tableau-de-bord", headers=entetes("dpo")).json()
    assert t["acces_actifs"] == 1
    assert t["echeances_proches"] == 1
    assert t["echeances"][0]["jours_restants"] == 3
    assert t["echeances"][0]["demandeur"] == "Paul Ferrand"


def test_tableau_de_bord_mesure_la_dette_de_purge(
    client, db_session, donnees, entetes, demande_valide
):
    demande_id = parcours_valide(client, entetes, demande_valide)
    deplacer_echeance(db_session, demande_id, -2)
    client.post("/autorisations/taches/expiration", headers=entetes("dpo"))

    t = client.get("/rapports/tableau-de-bord", headers=entetes("dpo")).json()
    assert t["dette_de_purge"] == 1


def test_tableau_de_bord_compte_les_soumissions_bloquees(
    client, donnees, entetes, demande_valide
):
    demande_valide["champs"][0]["mode"] = "BRUT"  # nom du patient en clair
    demande_id = client.post("/demandes", json=demande_valide,
                             headers=entetes("chercheur")).json()["id"]
    client.post(f"/demandes/{demande_id}/soumettre", headers=entetes("chercheur"))

    t = client.get("/rapports/tableau-de-bord", headers=entetes("dpo")).json()
    assert t["soumissions_bloquees"] == 1


def test_tableau_de_bord_interdit_au_chercheur(client, donnees, entetes):
    assert client.get("/rapports/tableau-de-bord",
                      headers=entetes("chercheur")).status_code == 403
