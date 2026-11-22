import base64

MDP = "Test2026!"

# Plus petit PNG valide (1 pixel)
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


def _data_url(octets, mime="image/png"):
    return f"data:{mime};base64," + base64.b64encode(octets).decode()


# --- Support ---
def test_chercheur_ouvre_un_ticket_et_ladmin_repond(client, donnees, entetes):
    r = client.post("/support/tickets", headers=entetes("chercheur"), json={
        "categorie": "SUPPRESSION", "sujet": "Supprimer ma demande",
        "message": "Pouvez-vous supprimer ma demande DA-2026-0001 ?"})
    assert r.status_code == 201, r.text
    tid = r.json()["id"]

    # L'autre chercheur ne le voit pas, l'admin oui
    assert client.get("/support/tickets", headers=entetes("chercheur2")).json() == []
    assert len(client.get("/support/tickets", headers=entetes("admin")).json()) == 1
    assert client.get("/support/a-traiter", headers=entetes("admin")).json()["a_traiter"] == 1

    r = client.post(f"/support/tickets/{tid}/messages", headers=entetes("admin"),
                    json={"message": "C'est fait."})
    assert r.status_code == 200
    assert len(r.json()["messages"]) == 2
    assert client.get("/support/a-traiter", headers=entetes("chercheur")).json()["a_traiter"] == 1

    r = client.post(f"/support/tickets/{tid}/statut", headers=entetes("admin"),
                    json={"statut": "CLOS"})
    assert r.json()["statut"] == "CLOS"
    # Un nouveau message du chercheur rouvre l'échange
    r = client.post(f"/support/tickets/{tid}/messages", headers=entetes("chercheur"),
                    json={"message": "Merci !"})
    assert r.json()["statut"] == "OUVERT"


def test_support_cloisonne(client, donnees, entetes):
    tid = client.post("/support/tickets", headers=entetes("chercheur"), json={
        "sujet": "Question", "message": "Bonjour"}).json()["id"]
    r = client.post(f"/support/tickets/{tid}/messages", headers=entetes("chercheur2"),
                    json={"message": "intrus"})
    assert r.status_code == 404
    # Seul un chercheur ouvre un ticket ; seul l'admin change le statut
    assert client.post("/support/tickets", headers=entetes("dpo"), json={
        "sujet": "Question", "message": "Bonjour"}).status_code == 403
    assert client.post(f"/support/tickets/{tid}/statut", headers=entetes("chercheur"),
                       json={"statut": "CLOS"}).status_code == 403


# --- Profil ---
def test_profil_infos_et_modification(client, donnees, entetes):
    r = client.get("/auth/me", headers=entetes("chercheur"))
    assert r.json()["email"] == "p.ferrand@chu.fr" and r.json()["photo"] is None
    r = client.put("/auth/profil", headers=entetes("chercheur"),
                   json={"nom_complet": "Paul Ferrand-Roux", "service": "Cardiologie"})
    assert r.status_code == 200 and r.json()["nom_complet"] == "Paul Ferrand-Roux"
    assert r.json()["email"] == "p.ferrand@chu.fr"


def test_photo_valide_puis_supprimee(client, donnees, entetes):
    h = entetes("chercheur")
    r = client.put("/auth/photo", headers=h, json={"image": _data_url(PNG)})
    assert r.status_code == 200 and r.json()["photo"].startswith("data:image/png")
    r = client.delete("/auth/photo", headers=h)
    assert r.json()["photo"] is None


def test_photo_refusee(client, donnees, entetes):
    h = entetes("chercheur")
    # SVG refusé, faux PNG refusé, trop lourd refusé
    assert client.put("/auth/photo", headers=h,
                      json={"image": _data_url(b"<svg/>", "image/svg+xml")}).status_code == 422
    assert client.put("/auth/photo", headers=h,
                      json={"image": _data_url(b"pas une image")}).status_code == 422
    gros = PNG + b"0" * 160_000
    assert client.put("/auth/photo", headers=h,
                      json={"image": _data_url(gros)}).status_code == 413


def test_changement_de_mot_de_passe(client, donnees, entetes):
    h = entetes("chercheur")
    assert client.post("/auth/mot-de-passe", headers=h, json={
        "actuel": "faux-mot-de-passe1", "nouveau": "NouveauMdp2026"}).status_code == 403
    assert client.post("/auth/mot-de-passe", headers=h, json={
        "actuel": MDP, "nouveau": "courtcourt"}).status_code == 422  # pas de chiffre
    r = client.post("/auth/mot-de-passe", headers=h, json={
        "actuel": MDP, "nouveau": "NouveauMdp2026"})
    assert r.status_code == 204
    assert client.post("/auth/login", data={
        "username": "p.ferrand@chu.fr", "password": MDP}).status_code == 401
    assert client.post("/auth/login", data={
        "username": "p.ferrand@chu.fr", "password": "NouveauMdp2026"}).status_code == 200
