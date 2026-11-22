"""Inscription libre, rôles, services hospitaliers, jeux publics, horodatage UTC."""
from datetime import date, timedelta

from app.models import (
    CategorieChamp, Champ, DecesStat, LotDonnees, MedicamentPathologie, Patient,
    Sejour,
)

MDP = "MotDePasse2026"


def _inscription(**surcharges):
    corps = {"nom_complet": "Camille Martin", "email": "camille.martin@etu.univ-cotedazur.fr",
             "service": "Master santé publique", "mot_de_passe": MDP, "engagement": True}
    corps.update(surcharges)
    return corps


def _entetes_de(client, corps):
    r = client.post("/auth/inscription", json=corps)
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _demande(donnees, champs, lot=None, **surcharges):
    corps = {
        "lot_id": (lot or donnees["lot"]).id,
        "titre_projet": "Analyse des parcours de soins",
        "finalite": ("Comparer les durées de séjour entre services afin d'identifier "
                     "des pistes d'amélioration du parcours de soin."),
        "date_debut_souhaitee": str(date.today()),
        "date_fin_souhaitee": str(date.today() + timedelta(days=120)),
        "champs": champs,
    }
    corps.update(surcharges)
    return corps


def _accorder(client, entetes, corps, qui="chercheur"):
    demande_id = client.post("/demandes", json=corps, headers=entetes(qui)).json()["id"]
    client.post(f"/demandes/{demande_id}/soumettre", headers=entetes(qui))
    r = client.post(f"/demandes/{demande_id}/valider", headers=entetes("dpo"),
                    json={"motif": "Demande proportionnée, identités masquées."})
    assert r.status_code == 200, r.text
    return demande_id


def _lot_multiservices(db, champs_extra=()):
    """Un lot sans service imposé : le demandeur choisit ses services."""
    lot = LotDonnees(code="MULTI", libelle="Séjours (tous services)", service_source="")
    lot.champs = [
        Champ(code="service", libelle="Service", categorie=CategorieChamp.ADMINISTRATIF,
              source="sejour.service"),
        Champ(code="duree", libelle="Durée", categorie=CategorieChamp.ADMINISTRATIF,
              source="sejour.duree_sejour"),
        *champs_extra,
    ]
    db.add(lot)
    patient = db.query(Patient).first()
    db.add(Sejour(patient=patient, service="Urgences", date_entree=date(2025, 6, 1),
                  duree_sejour=1, diagnostic_cim10="R07",
                  diagnostic_libelle="Douleur thoracique", traitements="Antalgiques",
                  mode_sortie="Domicile"))
    db.commit()
    db.refresh(lot)
    return lot, {c.code: c.id for c in lot.champs}


# ------------------------------------------------------------------ inscription
def test_inscription_cree_un_demandeur_deja_connecte(client):
    entetes = _entetes_de(client, _inscription(email="Camille.Martin@Gmail.com"))
    moi = client.get("/auth/me", headers=entetes).json()
    assert moi["role"] == "CHERCHEUR"
    assert moi["email"] == "camille.martin@gmail.com"  # adresse personnelle acceptée


def test_inscription_puis_connexion_classique(client):
    client.post("/auth/inscription", json=_inscription())
    r = client.post("/auth/login", data={
        "username": "  CAMILLE.MARTIN@etu.univ-cotedazur.fr ", "password": MDP})
    assert r.status_code == 200


def test_inscription_ne_permet_pas_de_choisir_son_role(client):
    corps = _inscription(role="DPO")  # champ inconnu : ignoré
    entetes = _entetes_de(client, corps)
    assert client.get("/auth/me", headers=entetes).json()["role"] == "CHERCHEUR"


def test_inscription_exige_lengagement(client):
    r = client.post("/auth/inscription", json=_inscription(engagement=False))
    assert r.status_code == 422


def test_inscription_refuse_un_mot_de_passe_faible(client):
    assert client.post("/auth/inscription",
                       json=_inscription(mot_de_passe="court1")).status_code == 422
    assert client.post("/auth/inscription",
                       json=_inscription(mot_de_passe="uniquementdeslettres")).status_code == 422


def test_inscription_refuse_une_adresse_deja_utilisee(client):
    client.post("/auth/inscription", json=_inscription())
    r = client.post("/auth/inscription",
                    json=_inscription(email="CAMILLE.MARTIN@etu.univ-cotedazur.fr"))
    assert r.status_code == 409


def test_un_compte_neuf_ne_voit_aucune_donnee(client, donnees):
    entetes = _entetes_de(client, _inscription())
    assert client.get("/demandes", headers=entetes).json() == []
    assert client.get("/autorisations", headers=entetes).json() == []
    assert client.get("/journal", headers=entetes).status_code == 403


# ------------------------------------------------------------------ rôles
def test_ladministrateur_liste_les_comptes(client, donnees, entetes):
    client.post("/auth/inscription", json=_inscription())
    comptes = client.get("/utilisateurs", headers=entetes("admin")).json()
    assert "camille.martin@etu.univ-cotedazur.fr" in {c["email"] for c in comptes}
    assert client.get("/utilisateurs", headers=entetes("dpo")).status_code == 403
    assert client.get("/utilisateurs", headers=entetes("chercheur")).status_code == 403


def test_ladministrateur_desactive_un_compte(client, donnees, entetes):
    client.post("/auth/inscription", json=_inscription())
    compte = next(c for c in client.get("/utilisateurs", headers=entetes("admin")).json()
                  if c["email"].startswith("camille"))
    r = client.patch(f"/utilisateurs/{compte['id']}", headers=entetes("admin"),
                     json={"actif": False})
    assert r.status_code == 200 and r.json()["actif"] is False

    connexion = client.post("/auth/login", data={
        "username": compte["email"], "password": MDP})
    assert connexion.status_code == 403
    actions = {e["action"] for e in client.get("/journal", headers=entetes("dpo")).json()}
    assert {"COMPTE_CREE", "COMPTE_MODIFIE"} <= actions


def test_ladministrateur_change_un_role(client, donnees, entetes):
    cible = donnees["users"]["chercheur2"]
    r = client.patch(f"/utilisateurs/{cible.id}", headers=entetes("admin"),
                     json={"role": "DPO"})
    assert r.json()["role"] == "DPO"


def test_ladministrateur_ne_se_modifie_pas_lui_meme(client, donnees, entetes):
    moi = donnees["users"]["admin"]
    r = client.patch(f"/utilisateurs/{moi.id}", headers=entetes("admin"),
                     json={"actif": False})
    assert r.status_code == 409


def test_ladministrateur_et_le_dpo_ne_deposent_pas_de_demande(
    client, donnees, entetes, demande_valide
):
    for qui in ("admin", "dpo"):
        r = client.post("/demandes", json=demande_valide, headers=entetes(qui))
        assert r.status_code == 403


def test_ladministrateur_ne_lit_pas_les_demandes(client, donnees, entetes):
    assert client.get("/demandes", headers=entetes("admin")).status_code == 403


def test_le_dpo_ne_voit_pas_les_brouillons(client, donnees, entetes, demande_valide):
    demande_id = client.post("/demandes", json=demande_valide,
                             headers=entetes("chercheur")).json()["id"]
    assert client.get("/demandes", headers=entetes("dpo")).json() == []
    assert client.get(f"/demandes/{demande_id}", headers=entetes("dpo")).status_code == 404

    client.post(f"/demandes/{demande_id}/soumettre", headers=entetes("chercheur"))
    assert len(client.get("/demandes", headers=entetes("dpo")).json()) == 1


def test_seul_le_proprietaire_transmet_ou_modifie(client, donnees, entetes, demande_valide):
    demande_id = client.post("/demandes", json=demande_valide,
                             headers=entetes("chercheur")).json()["id"]
    assert client.post(f"/demandes/{demande_id}/soumettre",
                       headers=entetes("dpo")).status_code == 403
    assert client.post(f"/demandes/{demande_id}/soumettre",
                       headers=entetes("chercheur2")).status_code == 404
    assert client.patch(f"/demandes/{demande_id}", headers=entetes("chercheur2"),
                        json={"titre_projet": "Titre pris en otage"}).status_code == 404


def test_le_dpo_decide_mais_ne_lit_pas_les_donnees(client, donnees, entetes, demande_valide):
    demande_id = _accorder(client, entetes, demande_valide)
    assert client.get(f"/extractions/{demande_id}",
                      headers=entetes("chercheur")).status_code == 200
    for qui in ("dpo", "admin"):
        assert client.get(f"/extractions/{demande_id}", headers=entetes(qui)).status_code == 403
        assert client.get(f"/extractions/{demande_id}/export",
                          headers=entetes(qui)).status_code == 403


# ------------------------------------------------------------------ services hospitaliers
def test_le_catalogue_liste_les_services_du_lot(client, db_session, donnees, entetes):
    lot, _ = _lot_multiservices(db_session)
    services = client.get(f"/lots/{lot.id}", headers=entetes("chercheur")).json()["services"]
    assert services == ["Cardiologie", "Urgences"]
    # lot dont le service est imposé : pas de choix
    imposé = client.get(f"/lots/{donnees['lot'].id}", headers=entetes("chercheur")).json()
    assert imposé["services"] == ["Cardiologie"]


def test_les_services_choisis_filtrent_lextraction(client, db_session, donnees, entetes):
    lot, ch = _lot_multiservices(db_session)
    champs = [{"champ_id": ch["service"], "mode": "BRUT"},
              {"champ_id": ch["duree"], "mode": "BRUT"}]

    urgences = _accorder(client, entetes,
                         _demande(donnees, champs, lot, services=["Urgences"]))
    e = client.get(f"/extractions/{urgences}", headers=entetes("chercheur")).json()
    assert {l["service"] for l in e["lignes"]} == {"Urgences"}
    assert e["nb_total"] == 1

    tous = _accorder(client, entetes, _demande(donnees, champs, lot))
    e = client.get(f"/extractions/{tous}", headers=entetes("chercheur")).json()
    assert {l["service"] for l in e["lignes"]} == {"Cardiologie", "Urgences"}
    assert e["nb_total"] == 4


def test_un_service_inconnu_est_refuse(client, db_session, donnees, entetes):
    lot, ch = _lot_multiservices(db_session)
    r = client.post("/demandes", headers=entetes("chercheur"), json=_demande(
        donnees, [{"champ_id": ch["duree"], "mode": "BRUT"}], lot, services=["Cuisine"]))
    assert r.status_code == 400


def test_tous_les_services_declenche_un_avertissement(client, db_session, donnees, entetes):
    lot, ch = _lot_multiservices(db_session)
    champs = [{"champ_id": ch["duree"], "mode": "BRUT"}]

    sans = client.post("/demandes", headers=entetes("chercheur"),
                       json=_demande(donnees, champs, lot)).json()["id"]
    rapport = client.get(f"/demandes/{sans}/controle-rgpd", headers=entetes("chercheur")).json()
    assert "R9_TOUS_LES_SERVICES" in {a["code"] for a in rapport["alertes"]}
    assert rapport["conforme"] is True  # avertissement, pas blocage

    avec = client.post("/demandes", headers=entetes("chercheur"), json=_demande(
        donnees, champs, lot, services=["Urgences"])).json()["id"]
    rapport = client.get(f"/demandes/{avec}/controle-rgpd", headers=entetes("chercheur")).json()
    assert "R9_TOUS_LES_SERVICES" not in {a["code"] for a in rapport["alertes"]}


def test_les_services_se_modifient_sur_un_brouillon(client, db_session, donnees, entetes):
    lot, ch = _lot_multiservices(db_session)
    demande_id = client.post("/demandes", headers=entetes("chercheur"), json=_demande(
        donnees, [{"champ_id": ch["duree"], "mode": "BRUT"}], lot,
        services=["Urgences"])).json()["id"]
    r = client.patch(f"/demandes/{demande_id}", headers=entetes("chercheur"),
                     json={"services": ["Cardiologie", "Urgences", "Urgences"]})
    assert r.json()["services"] == ["Cardiologie", "Urgences"]  # sans doublon


# ------------------------------------------------------------------ protections en langage courant
def test_le_catalogue_dit_ce_que_le_demandeur_recoit(client, donnees, entetes):
    champs = client.get(f"/lots/{donnees['lot'].id}",
                        headers=entetes("chercheur")).json()["champs"]
    par_code = {c["code"]: c for c in champs}
    assert par_code["nom"]["protection"] == "Code anonyme"
    assert par_code["ddn"]["protection"] == "Année seulement"
    assert par_code["cp"]["protection"] == "Département seulement"
    assert par_code["sexe"]["protection"] == "Valeur exacte"
    assert par_code["diag"]["protection"] == "Valeur exacte"
    assert par_code["cp"]["reductible"] is True
    assert par_code["sexe"]["reductible"] is False


def test_la_demande_affiche_la_protection_choisie(client, donnees, entetes):
    ch = donnees["champs"]
    demande_id = client.post("/demandes", headers=entetes("chercheur"), json=_demande(donnees, [
        {"champ_id": ch["nom"], "mode": "PSEUDONYMISE"},
        {"champ_id": ch["ddn"], "mode": "PSEUDONYMISE"},
        {"champ_id": ch["cp"], "mode": "BRUT", "justification": "Analyse par commune."},
    ])).json()["id"]
    d = client.get(f"/demandes/{demande_id}", headers=entetes("chercheur")).json()
    protections = {c["champ"]["code"]: c["protection"] for c in d["champs_demandes"]}
    assert protections == {"nom": "Code anonyme", "ddn": "Année seulement",
                           "cp": "Valeur exacte"}
    assert d["reference"] == f"DA-{date.today().year}-{demande_id:04d}"


def test_la_date_dentree_est_reduite_au_mois(client, db_session, donnees, entetes):
    champ = Champ(lot_id=donnees["lot"].id, code="date_entree", libelle="Date d'entrée",
                  categorie=CategorieChamp.QUASI_IDENTIFIANT, source="sejour.date_entree")
    db_session.add(champ)
    db_session.commit()

    demande_id = _accorder(client, entetes, _demande(donnees, [
        {"champ_id": champ.id, "mode": "PSEUDONYMISE"}]))
    e = client.get(f"/extractions/{demande_id}", headers=entetes("chercheur")).json()
    assert {l["date_entree"] for l in e["lignes"]} == {"2025-04", "2025-09", "2025-07"}
    assert e["colonnes"][0]["transformation"] == "Mois et année"


# ------------------------------------------------------------------ jeux publics
def test_referentiel_medicaments(client, db_session, donnees, entetes):
    db_session.add_all([
        MedicamentPathologie(code_cis="60002504", pathologie="Reflux gastro-oesophagien"),
        MedicamentPathologie(code_cis="60003620", pathologie="Asthme"),
    ])
    lot = LotDonnees(code="MEDICAMENTS", libelle="Médicaments", source_donnees="MEDICAMENT")
    lot.champs = [
        Champ(code="code_cis", libelle="Code CIS", categorie=CategorieChamp.DONNEE_PUBLIQUE,
              source="medicament.code_cis"),
        Champ(code="pathologie", libelle="Maladie", categorie=CategorieChamp.DONNEE_PUBLIQUE,
              source="medicament.pathologie"),
    ]
    db_session.add(lot)
    db_session.commit()
    ch = {c.code: c.id for c in lot.champs}

    demande_id = _accorder(client, entetes, _demande(donnees, [
        {"champ_id": ch["code_cis"], "mode": "BRUT"},
        {"champ_id": ch["pathologie"], "mode": "BRUT"}], lot))
    e = client.get(f"/extractions/{demande_id}", headers=entetes("chercheur")).json()
    assert e["nb_total"] == 2
    assert {l["pathologie"] for l in e["lignes"]} == {"Reflux gastro-oesophagien", "Asthme"}
    assert e["colonnes"][0]["transformation"] == "Valeur exacte"


def test_statistiques_de_deces(client, db_session, donnees, entetes):
    db_session.add_all([
        DecesStat(annee=2024, cause="Tumeurs", sexe="Tous sexes", classe_age="Tous âges",
                  effectifs=173502, taux_standardise=224.6, age_median=76.0, part_cause=0.271),
        DecesStat(annee=2024, cause="COVID-19", sexe="Femmes", classe_age="85 ans et plus",
                  effectifs=None, taux_standardise=None, age_median=None, part_cause=None),
    ])
    lot = LotDonnees(code="DECES_FRANCE", libelle="Décès", source_donnees="DECES")
    lot.champs = [
        Champ(code="cause", libelle="Cause", categorie=CategorieChamp.DONNEE_PUBLIQUE,
              source="deces.cause"),
        Champ(code="effectifs", libelle="Décès", categorie=CategorieChamp.DONNEE_PUBLIQUE,
              source="deces.effectifs"),
    ]
    db_session.add(lot)
    db_session.commit()
    ch = {c.code: c.id for c in lot.champs}

    demande_id = _accorder(client, entetes, _demande(donnees, [
        {"champ_id": ch["cause"], "mode": "BRUT"},
        {"champ_id": ch["effectifs"], "mode": "BRUT"}], lot))
    e = client.get(f"/extractions/{demande_id}", headers=entetes("chercheur")).json()
    lignes = {l["cause"]: l["effectifs"] for l in e["lignes"]}
    assert lignes == {"Tumeurs": "173502", "COVID-19": ""}  # case vide conservée vide


# ------------------------------------------------------------------ horodatage
def test_les_dates_sortent_en_utc_explicite(client, donnees, entetes, demande_valide):
    """Sans fuseau, le navigateur lit l'heure UTC comme une heure locale : 2 h d'écart."""
    demande_id = client.post("/demandes", json=demande_valide,
                             headers=entetes("chercheur")).json()["id"]
    client.post(f"/demandes/{demande_id}/soumettre", headers=entetes("chercheur"))

    cree_le = client.get(f"/demandes/{demande_id}",
                         headers=entetes("chercheur")).json()["cree_le"]
    assert cree_le.endswith(("Z", "+00:00"))

    for entree in client.get("/journal", headers=entetes("dpo")).json():
        assert entree["horodatage"].endswith(("Z", "+00:00"))
