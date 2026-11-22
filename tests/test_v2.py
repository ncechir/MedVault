"""V2 : contrôle avant export, politiques de données, journal à intégrité vérifiable."""
from sqlalchemy import select

from app.models import JournalAudit
from tests.test_extraction import accorder, demande_avec


def _demande_quasi(client, donnees, entetes):
    ch = donnees["champs"]
    return accorder(client, entetes, demande_avec(donnees, [
        {"champ_id": ch["ddn"], "mode": "PSEUDONYMISE"},
        {"champ_id": ch["sexe"], "mode": "PSEUDONYMISE"},
        {"champ_id": ch["diag"], "mode": "BRUT", "justification": "Stratification."},
    ]))


def _politique(client, entetes, action, nom="Politique de test", **extra):
    r = client.post("/politiques", headers=entetes("dpo"), json={
        "nom": nom, "k_min": 5, "action": action, **extra})
    assert r.status_code == 201, r.text
    return r.json()


# ------------------------------------------------------- contrôle avant export
def test_lextraction_porte_un_controle_de_risque(client, donnees, entetes):
    did = _demande_quasi(client, donnees, entetes)
    r = client.get(f"/extractions/{did}", headers=entetes("chercheur"))
    assert r.status_code == 200
    c = r.json()["controle"]
    assert c["niveau"] in ("MODERE", "ELEVE")        # 3 lignes seulement
    assert c["k_min"] is not None and c["k_min"] < c["k_cible"]
    assert c["nb_lignes_supprimees"] == 0            # politique intégrée : avertir
    assert r.json()["nb_lignes"] == 3


def test_la_politique_supprimer_retire_les_petits_groupes(client, donnees, entetes):
    _politique(client, entetes, "SUPPRIMER")
    did = _demande_quasi(client, donnees, entetes)
    r = client.get(f"/extractions/{did}", headers=entetes("chercheur")).json()
    assert r["nb_lignes"] == 0 and r["lignes"] == []
    assert r["controle"]["nb_lignes_supprimees"] == 3
    csv = client.get(f"/extractions/{did}/export", headers=entetes("chercheur"))
    assert csv.status_code == 200
    assert len(csv.text.strip().splitlines()) == 1   # en-tête seul


def test_la_politique_bloquer_refuse_lexport_mais_pas_la_consultation(
        client, donnees, entetes):
    _politique(client, entetes, "BLOQUER")
    did = _demande_quasi(client, donnees, entetes)
    assert client.get(f"/extractions/{did}", headers=entetes("chercheur")).status_code == 200
    r = client.get(f"/extractions/{did}/export", headers=entetes("chercheur"))
    assert r.status_code == 409 and "politique" in r.json()["detail"].lower()
    journal = client.get("/journal?action=EXPORT_BLOQUE_POLITIQUE", headers=entetes("admin"))
    assert len(journal.json()) == 1


# ------------------------------------------------------------------ politiques
def test_seul_le_dpo_gere_les_politiques(client, donnees, entetes):
    corps = {"nom": "Tentative", "k_min": 5, "action": "AVERTIR"}
    assert client.post("/politiques", headers=entetes("chercheur"), json=corps).status_code == 403
    assert client.post("/politiques", headers=entetes("admin"), json=corps).status_code == 403
    assert client.get("/politiques", headers=entetes("admin")).status_code == 200
    assert client.get("/politiques", headers=entetes("chercheur")).status_code == 403


def test_premiere_politique_par_defaut_et_changement(client, donnees, entetes):
    a = _politique(client, entetes, "AVERTIR", nom="Politique A")
    b = _politique(client, entetes, "SUPPRIMER", nom="Politique B")
    assert a["par_defaut"] and not b["par_defaut"]
    assert client.delete(f"/politiques/{a['id']}", headers=entetes("dpo")).status_code == 409
    client.post(f"/politiques/{b['id']}/defaut", headers=entetes("dpo"))
    liste = {p["nom"]: p["par_defaut"] for p in
             client.get("/politiques", headers=entetes("dpo")).json()}
    assert liste == {"Politique A": False, "Politique B": True}
    assert client.delete(f"/politiques/{a['id']}", headers=entetes("dpo")).status_code == 204


def test_nom_de_politique_unique_et_k_minimum(client, donnees, entetes):
    _politique(client, entetes, "AVERTIR", nom="Doublon")
    r = client.post("/politiques", headers=entetes("dpo"),
                    json={"nom": "Doublon", "k_min": 5, "action": "AVERTIR"})
    assert r.status_code == 409
    r = client.post("/politiques", headers=entetes("dpo"),
                    json={"nom": "Trop faible", "k_min": 1, "action": "AVERTIR"})
    assert r.status_code == 422


# ----------------------------------------------------------- journal chaîné
def test_la_chaine_du_journal_est_valide(client, donnees, entetes):
    _demande_quasi(client, donnees, entetes)
    r = client.get("/journal/integrite", headers=entetes("admin"))
    assert r.status_code == 200
    i = r.json()
    assert i["valide"] and i["nb_anomalies"] == 0
    assert i["nb_chainees"] >= 5 and len(i["empreinte_tete"]) == 64


def test_la_modification_dune_entree_est_detectee(client, db_session, donnees, entetes):
    _demande_quasi(client, donnees, entetes)
    cible = db_session.scalars(select(JournalAudit).where(
        JournalAudit.action == "DEMANDE_VALIDEE")).first()
    cible.details = '{"motif": "falsifié"}'
    db_session.commit()
    i = client.get("/journal/integrite", headers=entetes("dpo")).json()
    assert not i["valide"]
    assert i["premiere_anomalie"]["id"] == cible.id


def test_la_suppression_dune_entree_est_detectee(client, db_session, donnees, entetes):
    _demande_quasi(client, donnees, entetes)
    milieu = db_session.scalars(select(JournalAudit).order_by(JournalAudit.id)).all()[3]
    db_session.delete(milieu)
    db_session.commit()
    i = client.get("/journal/integrite", headers=entetes("admin")).json()
    assert not i["valide"]


def test_les_entrees_anterieures_au_chainage_ne_cassent_pas_la_verification(
        client, db_session, donnees, entetes):
    db_session.add(JournalAudit(utilisateur_email="ancien@chu.fr", action="CONNEXION",
                                entite="utilisateur"))
    db_session.commit()
    i = client.get("/journal/integrite", headers=entetes("admin")).json()
    assert i["valide"] and i["nb_anterieures"] == 1


# --------------------------------------------------------------------- rapport
def test_rapport_daudit_pdf(client, donnees, entetes):
    _demande_quasi(client, donnees, entetes)
    for role in ("admin", "dpo"):
        r = client.get("/journal/rapport", headers=entetes(role))
        assert r.status_code == 200 and r.content.startswith(b"%PDF")
    assert client.get("/journal/rapport", headers=entetes("chercheur")).status_code == 403
