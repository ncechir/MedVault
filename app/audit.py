"""Journal d'audit à intégrité vérifiable.

Chaque entrée porte une empreinte SHA-256 calculée à partir de son contenu et
de l'empreinte de l'entrée précédente (chaînage). Modifier une entrée, en
supprimer une au milieu ou en glisser une fausse rompt la chaîne : la
vérification le signale et indique à partir de quelle entrée.

Limite assumée : un attaquant qui contrôle la base ET recalcule toute la chaîne
n'est pas détecté. L'« empreinte de tête » affichée par la vérification doit
donc être conservée hors de la base (rapport d'audit, coffre, e-mail) pour
détecter aussi une réécriture complète ou la suppression des dernières entrées.
"""
import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.models import JournalAudit, Utilisateur, maintenant

_CLE_TETE = "_audit_derniere_empreinte"


@event.listens_for(Session, "after_commit")
@event.listens_for(Session, "after_rollback")
def _oublier_tete(session: Session) -> None:
    # Après la fin de la transaction, une autre session a pu écrire : on relira la base.
    session.info.pop(_CLE_TETE, None)


def _naif_utc(h: datetime) -> datetime:
    if h.tzinfo is not None:
        h = h.astimezone(timezone.utc).replace(tzinfo=None)
    return h


def calculer_empreinte(precedente: str | None, horodatage: datetime, email: str,
                       action: str, entite: str, entite_id: int | None,
                       details: str) -> str:
    charge = json.dumps(
        [precedente or "", _naif_utc(horodatage).isoformat(), email or "", action,
         entite, entite_id, details or ""],
        ensure_ascii=False, separators=(",", ":"),
    )
    return hashlib.sha256(charge.encode("utf-8")).hexdigest()


def _derniere_empreinte(db: Session) -> str | None:
    if _CLE_TETE in db.info:
        return db.info[_CLE_TETE]
    with db.no_autoflush:
        return db.scalar(
            select(JournalAudit.empreinte)
            .where(JournalAudit.empreinte.is_not(None))
            .order_by(JournalAudit.id.desc()).limit(1)
        )


def journaliser(
    db: Session,
    utilisateur: Utilisateur | None,
    action: str,
    entite: str,
    entite_id: int | None = None,
    **details,
) -> JournalAudit:
    """Écrit une entrée d'audit chaînée. Appelé à chaque transition d'état."""
    horodatage = _naif_utc(maintenant())
    email = utilisateur.email if utilisateur else "systeme"
    texte = json.dumps(details, ensure_ascii=False, default=str)
    precedente = _derniere_empreinte(db)
    empreinte = calculer_empreinte(precedente, horodatage, email, action, entite,
                                   entite_id, texte)
    entree = JournalAudit(
        horodatage=horodatage,
        utilisateur_id=utilisateur.id if utilisateur else None,
        utilisateur_email=email,
        action=action,
        entite=entite,
        entite_id=entite_id,
        details=texte,
        empreinte_precedente=precedente or "",
        empreinte=empreinte,
    )
    db.add(entree)
    db.info[_CLE_TETE] = empreinte
    return entree


def verifier_chaine(db: Session) -> dict:
    """Recalcule toute la chaîne et signale les ruptures."""
    entrees = db.scalars(select(JournalAudit).order_by(JournalAudit.id)).all()
    nb_chainees = nb_anterieures = 0
    anomalies: list[dict] = []
    precedente: str | None = None

    for e in entrees:
        if e.empreinte is None:
            if nb_chainees:
                anomalies.append({"id": e.id, "motif": "Entrée sans empreinte insérée "
                                  "après le début du chaînage"})
            else:
                nb_anterieures += 1
            continue

        if nb_chainees == 0:
            # Première entrée chaînée : son prédécesseur est vide par construction
            if (e.empreinte_precedente or "") != "":
                anomalies.append({"id": e.id, "motif": "Début de chaîne incohérent"})
        elif (e.empreinte_precedente or "") != (precedente or ""):
            anomalies.append({"id": e.id, "motif": "Maillon manquant ou entrée "
                              "intercalée : la chaîne est rompue ici"})

        attendue = calculer_empreinte(
            e.empreinte_precedente, e.horodatage, e.utilisateur_email, e.action,
            e.entite, e.entite_id, e.details)
        if attendue != e.empreinte:
            anomalies.append({"id": e.id, "motif": "Contenu de l'entrée modifié "
                              "après son enregistrement"})

        precedente = e.empreinte
        nb_chainees += 1

    return {
        "valide": not anomalies,
        "nb_total": len(entrees),
        "nb_chainees": nb_chainees,
        "nb_anterieures": nb_anterieures,
        "nb_anomalies": len(anomalies),
        "premiere_anomalie": anomalies[0] if anomalies else None,
        "empreinte_tete": precedente or "",
        "verifie_le": maintenant(),
        "avertissement": (
            "La vérification détecte la modification ou la suppression d'entrées "
            "intermédiaires. Conservez l'empreinte de tête hors de la base pour "
            "détecter aussi la suppression des dernières entrées."
        ),
    }
