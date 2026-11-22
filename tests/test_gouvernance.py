"""Gouvernance : indicateur de masquage des identités, date de suppression,
décision du responsable des données."""
from datetime import date, timedelta

from app.config import DELAI_PURGE_JOURS


# ------------------------------------------------------- indicateur de masquage
def _creer_demande(client, entetes, demande_valide, mode_nom):
    corps = dict(demande_valide)
    corps["champs"] = [
        {"champ_id": c["champ_id"],
         "mode": mode_nom if i == 0 else c["mode"],
         "justification": c.get("justification", "")}
        for i, c in enumerate(demande_valide["champs"])
    ]
    r = client.post("/demandes", json=corps, headers=entetes("chercheur"))
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_identites_masquees_quand_pseudonymisees(client, entetes, demande_valide):
    demande_id = _creer_demande(client, entetes, demande_valide, "PSEUDONYMISE")
    rapport = client.get(f"/demandes/{demande_id}/controle-rgpd",
                         headers=entetes("chercheur")).json()
    assert rapport["identites_masquees"] is True
    assert rapport["nb_identifiants_masques"] == 1


def test_identites_exposees_quand_en_clair(client, entetes, demande_valide):
    demande_id = _creer_demande(client, entetes, demande_valide, "BRUT")
    rapport = client.get(f"/demandes/{demande_id}/controle-rgpd",
                         headers=entetes("chercheur")).json()
    assert rapport["identites_masquees"] is False
    assert rapport["conforme"] is False


# --------------------------------------------------------- suppression des données
def test_la_date_de_purge_est_exposee(client, entetes, demande_valide):
    demande_id = _creer_demande(client, entetes, demande_valide, "PSEUDONYMISE")
    client.post(f"/demandes/{demande_id}/soumettre", headers=entetes("chercheur"))
    client.post(f"/demandes/{demande_id}/valider", headers=entetes("dpo"),
                json={"motif": "Demande proportionnée et conforme."})

    acces = client.get("/autorisations", headers=entetes("dpo")).json()[0]
    fin = date.fromisoformat(acces["date_fin"])
    assert acces["date_purge_prevue"] == str(fin + timedelta(days=DELAI_PURGE_JOURS))


def test_le_dpo_fixe_la_fin_daccès_et_les_conditions(client, entetes, demande_valide):
    demande_id = _creer_demande(client, entetes, demande_valide, "PSEUDONYMISE")
    client.post(f"/demandes/{demande_id}/soumettre", headers=entetes("chercheur"))
    fin = date.today() + timedelta(days=60)
    r = client.post(f"/demandes/{demande_id}/valider", headers=entetes("dpo"), json={
        "motif": "Accord limité dans le temps.",
        "date_fin_acces": str(fin),
        "conditions": "Aucune sortie de l'extraction hors du poste sécurisé.",
        "sous_condition": True,
    })
    assert r.status_code == 200, r.text
    assert r.json()["sens"] == "VALIDEE_SOUS_CONDITION"

    acces = client.get("/autorisations", headers=entetes("dpo")).json()[0]
    assert acces["date_fin"] == str(fin)
