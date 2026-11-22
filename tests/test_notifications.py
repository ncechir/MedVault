"""Tests des tickets MED-9 (motif de refus visible) et MED-8 (notification
d'expiration d'accès)."""
from datetime import date, timedelta

from app.models import Autorisation, StatutAutorisation


def creer_et_soumettre(client, entetes, corps):
    demande_id = client.post("/demandes", json=corps,
                             headers=entetes("chercheur")).json()["id"]
    client.post(f"/demandes/{demande_id}/soumettre", headers=entetes("chercheur"))
    return demande_id


# ---------------------------------------------------------------- MED-9
def test_le_chercheur_lit_le_motif_du_refus(client, donnees, entetes, demande_valide):
    demande_id = creer_et_soumettre(client, entetes, demande_valide)
    motif = "Finalité déjà couverte par l'étude REHOSP-2025 en cours."
    client.post(f"/demandes/{demande_id}/refuser", headers=entetes("dpo"),
                json={"motif": motif})

    d = client.get(f"/demandes/{demande_id}", headers=entetes("chercheur")).json()
    assert d["statut"] == "REFUSEE"
    assert d["decision"]["sens"] == "REFUSEE"
    assert d["decision"]["motif"] == motif
    assert d["decision"]["dpo"]["nom_complet"] == "Nadia Belkacem"


def test_le_refus_genere_une_notification(client, donnees, entetes, demande_valide):
    demande_id = creer_et_soumettre(client, entetes, demande_valide)
    client.post(f"/demandes/{demande_id}/refuser", headers=entetes("dpo"),
                json={"motif": "Les colonnes demandées excèdent la finalité."})

    notifs = client.get("/notifications", headers=entetes("chercheur")).json()
    assert len(notifs) == 1
    assert notifs[0]["type"] == "DECISION_REFUSEE"
    assert "excèdent" in notifs[0]["message"]


def test_la_validation_expose_la_decision(client, donnees, entetes, demande_valide):
    demande_id = creer_et_soumettre(client, entetes, demande_valide)
    client.post(f"/demandes/{demande_id}/valider", headers=entetes("dpo"),
                json={"motif": "Demande proportionnée et identités pseudonymisées."})

    d = client.get(f"/demandes/{demande_id}", headers=entetes("chercheur")).json()
    assert d["decision"]["sens"] == "VALIDEE"
    assert d["autorisation"]["statut"] == "ACTIVE"


def test_un_chercheur_ne_lit_pas_les_notifications_dun_autre(
    client, donnees, entetes, demande_valide
):
    demande_id = creer_et_soumettre(client, entetes, demande_valide)
    client.post(f"/demandes/{demande_id}/refuser", headers=entetes("dpo"),
                json={"motif": "Motif de refus destiné au seul demandeur."})
    assert client.get("/notifications", headers=entetes("chercheur2")).json() == []


# ---------------------------------------------------------------- MED-8
def _autorisation_expirant_dans(db_session, demande_id, jours):
    autorisation = db_session.query(Autorisation).filter_by(demande_id=demande_id).one()
    autorisation.date_fin = date.today() + timedelta(days=jours)
    db_session.commit()
    return autorisation


def test_preavis_avant_echeance(client, db_session, donnees, entetes, demande_valide):
    demande_id = creer_et_soumettre(client, entetes, demande_valide)
    client.post(f"/demandes/{demande_id}/valider", headers=entetes("dpo"),
                json={"motif": "Validation en vue du test de préavis."})
    _autorisation_expirant_dans(db_session, demande_id, 3)

    client.post("/autorisations/taches/expiration", headers=entetes("dpo"))
    types = [n["type"] for n in
             client.get("/notifications", headers=entetes("chercheur")).json()]
    assert "ACCES_BIENTOT_EXPIRE" in types


def test_preavis_non_duplique(client, db_session, donnees, entetes, demande_valide):
    demande_id = creer_et_soumettre(client, entetes, demande_valide)
    client.post(f"/demandes/{demande_id}/valider", headers=entetes("dpo"),
                json={"motif": "Validation en vue du test d'idempotence."})
    _autorisation_expirant_dans(db_session, demande_id, 3)

    for _ in range(3):
        client.post("/autorisations/taches/expiration", headers=entetes("dpo"))

    notifs = client.get("/notifications", headers=entetes("chercheur")).json()
    preavis = [n for n in notifs if n["type"] == "ACCES_BIENTOT_EXPIRE"]
    assert len(preavis) == 1


def test_cloture_et_notification_a_echeance(
    client, db_session, donnees, entetes, demande_valide
):
    demande_id = creer_et_soumettre(client, entetes, demande_valide)
    client.post(f"/demandes/{demande_id}/valider", headers=entetes("dpo"),
                json={"motif": "Validation en vue du test de clôture."})
    _autorisation_expirant_dans(db_session, demande_id, -1)

    resume = client.post("/autorisations/taches/expiration",
                         headers=entetes("dpo")).json()
    assert len(resume["acces_clotures"]) == 1
    assert resume["acces_clotures"][0]["statut"] == "EXPIREE"

    types = [n["type"] for n in
             client.get("/notifications", headers=entetes("chercheur")).json()]
    assert "ACCES_EXPIRE" in types


def test_liste_des_echeances(client, db_session, donnees, entetes, demande_valide):
    demande_id = creer_et_soumettre(client, entetes, demande_valide)
    client.post(f"/demandes/{demande_id}/valider", headers=entetes("dpo"),
                json={"motif": "Validation en vue du test des échéances."})
    _autorisation_expirant_dans(db_session, demande_id, 5)

    echeances = client.get("/autorisations/echeances", headers=entetes("dpo")).json()
    assert len(echeances) == 1
    assert echeances[0]["jours_restants"] == 5
    assert echeances[0]["demandeur"] == "Paul Ferrand"


def test_compteur_de_notifications_non_lues(
    client, donnees, entetes, demande_valide
):
    demande_id = creer_et_soumettre(client, entetes, demande_valide)
    client.post(f"/demandes/{demande_id}/refuser", headers=entetes("dpo"),
                json={"motif": "Motif de refus pour le test du compteur."})

    assert client.get("/notifications/compte",
                      headers=entetes("chercheur")).json()["non_lues"] == 1

    notif_id = client.get("/notifications", headers=entetes("chercheur")).json()[0]["id"]
    client.post(f"/notifications/{notif_id}/lue", headers=entetes("chercheur"))

    assert client.get("/notifications/compte",
                      headers=entetes("chercheur")).json()["non_lues"] == 0
