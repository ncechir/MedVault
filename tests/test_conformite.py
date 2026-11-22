from datetime import date, timedelta


def codes(rapport) -> set[str]:
    return {a["code"] for a in rapport["alertes"]}


def creer(client, entetes, corps):
    r = client.post("/demandes", json=corps, headers=entetes("chercheur"))
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_demande_conforme(client, donnees, entetes, demande_valide):
    demande_id = creer(client, entetes, demande_valide)
    r = client.get(f"/demandes/{demande_id}/controle-rgpd",
                   headers=entetes("chercheur"))
    assert r.json()["conforme"] is True
    assert r.json()["nb_bloquants"] == 0


def test_nom_en_clair_bloque(client, donnees, entetes, demande_valide):
    demande_valide["champs"][0]["mode"] = "BRUT"  # le nom en clair
    demande_id = creer(client, entetes, demande_valide)
    rapport = client.get(f"/demandes/{demande_id}/controle-rgpd",
                         headers=entetes("chercheur")).json()
    assert rapport["conforme"] is False
    assert "R2_IDENTITE_EN_CLAIR" in codes(rapport)


def test_duree_excessive_bloque(client, donnees, entetes, demande_valide):
    demande_valide["date_fin_souhaitee"] = str(date.today() + timedelta(days=1500))
    demande_id = creer(client, entetes, demande_valide)
    rapport = client.get(f"/demandes/{demande_id}/controle-rgpd",
                         headers=entetes("chercheur")).json()
    assert "R3_DUREE_EXCESSIVE" in codes(rapport)


def test_finalite_imprecise_bloque(client, donnees, entetes, demande_valide):
    demande_valide["finalite"] = "Étude interne."
    demande_id = creer(client, entetes, demande_valide)
    rapport = client.get(f"/demandes/{demande_id}/controle-rgpd",
                         headers=entetes("chercheur")).json()
    assert "R4_FINALITE_IMPRECISE" in codes(rapport)


def test_croisement_quasi_identifiants_avertit(client, donnees, entetes, demande_valide):
    ch = donnees["champs"]
    demande_valide["champs"] += [
        {"champ_id": ch["ddn"], "mode": "BRUT"},
        {"champ_id": ch["cp"], "mode": "BRUT"},
        {"champ_id": ch["sexe"], "mode": "BRUT"},
    ]
    demande_id = creer(client, entetes, demande_valide)
    rapport = client.get(f"/demandes/{demande_id}/controle-rgpd",
                         headers=entetes("chercheur")).json()
    assert "R5_RISQUE_REIDENTIFICATION" in codes(rapport)
    assert rapport["conforme"] is True  # avertissement, pas blocage


def test_sante_sans_justification_avertit(client, donnees, entetes, demande_valide):
    demande_valide["champs"][1]["justification"] = ""
    demande_id = creer(client, entetes, demande_valide)
    rapport = client.get(f"/demandes/{demande_id}/controle-rgpd",
                         headers=entetes("chercheur")).json()
    assert "R7_SANTE_SANS_JUSTIFICATION" in codes(rapport)


def test_demande_vide_bloque(client, donnees, entetes, demande_valide):
    demande_valide["champs"] = []
    demande_id = creer(client, entetes, demande_valide)
    rapport = client.get(f"/demandes/{demande_id}/controle-rgpd",
                         headers=entetes("chercheur")).json()
    assert "R1_AUCUN_CHAMP" in codes(rapport)
