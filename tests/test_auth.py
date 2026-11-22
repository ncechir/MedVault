def test_login_reussi(client, donnees):
    r = client.post("/auth/login",
                    data={"username": "dpo@chu.fr", "password": "Test2026!"})
    assert r.status_code == 200
    assert r.json()["token_type"] == "bearer"


def test_login_mauvais_mot_de_passe(client, donnees):
    r = client.post("/auth/login",
                    data={"username": "dpo@chu.fr", "password": "faux"})
    assert r.status_code == 401


def test_endpoint_protege_sans_token(client, donnees):
    assert client.get("/lots").status_code == 401


def test_journal_interdit_au_chercheur(client, donnees, entetes):
    assert client.get("/journal", headers=entetes("chercheur")).status_code == 403


def test_journal_autorise_au_dpo(client, donnees, entetes):
    assert client.get("/journal", headers=entetes("dpo")).status_code == 200


def test_chercheur_ne_voit_pas_la_demande_dun_collegue(
    client, donnees, entetes, demande_valide
):
    r = client.post("/demandes", json=demande_valide, headers=entetes("chercheur"))
    demande_id = r.json()["id"]

    autre = client.get(f"/demandes/{demande_id}", headers=entetes("chercheur2"))
    assert autre.status_code == 404  # on ne révèle pas son existence

    proprietaire = client.get(f"/demandes/{demande_id}", headers=entetes("chercheur"))
    assert proprietaire.status_code == 200
