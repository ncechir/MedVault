def _deposer(client, entetes, demande_valide):
    r = client.post("/demandes", headers=entetes("chercheur"), json=demande_valide)
    assert r.status_code == 201, r.text
    return r.json()


def test_admin_supprime_une_demande(client, donnees, entetes, demande_valide):
    d = _deposer(client, entetes, demande_valide)
    h = entetes("admin")
    liste = client.get("/admin/demandes", headers=h).json()
    assert [x["reference"] for x in liste] == [d["reference"]]
    assert "finalite" not in liste[0]  # l'administrateur ne lit pas le contenu

    # Mauvaise référence : refus
    assert client.delete(f"/admin/demandes/{d['id']}?confirmation=DA-0000",
                         headers=h).status_code == 400
    r = client.delete(f"/admin/demandes/{d['id']}?confirmation={d['reference']}", headers=h)
    assert r.status_code == 204
    assert client.get("/admin/demandes", headers=h).json() == []
    # La suppression est tracée
    journal = client.get("/journal", headers=entetes("dpo")).json()
    assert any(e["action"] == "DEMANDE_SUPPRIMEE" for e in journal)


def test_suppression_reservee_a_ladmin(client, donnees, entetes, demande_valide):
    d = _deposer(client, entetes, demande_valide)
    for role in ("chercheur", "dpo"):
        h = entetes(role)
        assert client.get("/admin/demandes", headers=h).status_code == 403
        assert client.delete(f"/admin/demandes/{d['id']}?confirmation={d['reference']}",
                             headers=h).status_code == 403
