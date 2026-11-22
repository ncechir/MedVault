from datetime import date, timedelta


def creer(client, entetes, corps):
    return client.post("/demandes", json=corps,
                       headers=entetes("chercheur")).json()["id"]


def test_parcours_complet(client, donnees, entetes, demande_valide):
    demande_id = creer(client, entetes, demande_valide)

    assert client.post(f"/demandes/{demande_id}/soumettre",
                       headers=entetes("chercheur")).json()["statut"] == "SOUMISE"

    assert client.post(f"/demandes/{demande_id}/instruire",
                       headers=entetes("dpo")).json()["statut"] == "EN_INSTRUCTION"

    r = client.post(f"/demandes/{demande_id}/valider", headers=entetes("dpo"), json={
        "motif": "Finalité légitime, données pseudonymisées, durée proportionnée.",
        "date_fin_acces": str(date.today() + timedelta(days=90)),
    })
    assert r.status_code == 200
    assert r.json()["sens"] == "VALIDEE"

    autorisations = client.get("/autorisations", headers=entetes("chercheur")).json()
    assert len(autorisations) == 1
    assert autorisations[0]["statut"] == "ACTIVE"


def test_soumission_bloquee_si_identite_en_clair(
    client, donnees, entetes, demande_valide
):
    demande_valide["champs"][0]["mode"] = "BRUT"
    demande_id = creer(client, entetes, demande_valide)
    r = client.post(f"/demandes/{demande_id}/soumettre", headers=entetes("chercheur"))
    assert r.status_code == 422
    assert client.get(f"/demandes/{demande_id}",
                      headers=entetes("chercheur")).json()["statut"] == "BROUILLON"


def test_chercheur_ne_peut_pas_valider(client, donnees, entetes, demande_valide):
    demande_id = creer(client, entetes, demande_valide)
    client.post(f"/demandes/{demande_id}/soumettre", headers=entetes("chercheur"))
    r = client.post(f"/demandes/{demande_id}/valider", headers=entetes("chercheur"),
                    json={"motif": "Je m'auto-valide, c'est plus rapide."})
    assert r.status_code == 403


def test_demande_soumise_non_modifiable(client, donnees, entetes, demande_valide):
    demande_id = creer(client, entetes, demande_valide)
    client.post(f"/demandes/{demande_id}/soumettre", headers=entetes("chercheur"))
    r = client.patch(f"/demandes/{demande_id}", headers=entetes("chercheur"),
                     json={"titre_projet": "Titre modifié après coup"})
    assert r.status_code == 409


def test_date_fin_accordee_ne_depasse_pas_la_demande(
    client, donnees, entetes, demande_valide
):
    demande_id = creer(client, entetes, demande_valide)
    client.post(f"/demandes/{demande_id}/soumettre", headers=entetes("chercheur"))
    r = client.post(f"/demandes/{demande_id}/valider", headers=entetes("dpo"), json={
        "motif": "Validation avec une durée rallongée d'office.",
        "date_fin_acces": str(date.today() + timedelta(days=900)),
    })
    assert r.status_code == 400


def test_refus_puis_pas_dautorisation(client, donnees, entetes, demande_valide):
    demande_id = creer(client, entetes, demande_valide)
    client.post(f"/demandes/{demande_id}/soumettre", headers=entetes("chercheur"))
    r = client.post(f"/demandes/{demande_id}/refuser", headers=entetes("dpo"),
                    json={"motif": "Finalité déjà couverte par une étude existante."})
    assert r.json()["sens"] == "REFUSEE"
    assert client.get("/autorisations", headers=entetes("chercheur")).json() == []


def test_revocation_puis_purge(client, donnees, entetes, demande_valide):
    demande_id = creer(client, entetes, demande_valide)
    client.post(f"/demandes/{demande_id}/soumettre", headers=entetes("chercheur"))
    client.post(f"/demandes/{demande_id}/valider", headers=entetes("dpo"),
                json={"motif": "Validation initiale de la demande d'accès."})
    auto_id = client.get("/autorisations", headers=entetes("dpo")).json()[0]["id"]

    r = client.post(f"/autorisations/{auto_id}/revoquer", headers=entetes("dpo"),
                    json={"motif": "Fin anticipée du projet de recherche."})
    assert r.json()["statut"] == "REVOQUEE"

    r = client.post(f"/autorisations/{auto_id}/purger", headers=entetes("dpo"))
    assert r.json()["statut"] == "PURGEE"
    assert r.json()["purge_effectuee_le"] is not None


def test_journal_trace_les_etapes(client, donnees, entetes, demande_valide):
    demande_id = creer(client, entetes, demande_valide)
    client.post(f"/demandes/{demande_id}/soumettre", headers=entetes("chercheur"))
    client.post(f"/demandes/{demande_id}/valider", headers=entetes("dpo"),
                json={"motif": "Validation conforme aux règles de gouvernance."})

    actions = {e["action"] for e in
               client.get("/journal", headers=entetes("dpo")).json()}
    assert {"DEMANDE_CREEE", "DEMANDE_SOUMISE", "DEMANDE_VALIDEE"} <= actions
