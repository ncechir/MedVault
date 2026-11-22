"""Envoi (ou simulation) des e-mails de la plateforme.

Sans serveur SMTP configuré (variables SMTP_* vides), aucun e-mail ne part
réellement : chacun est néanmoins consigné dans la table `email_envoye`
et reste consultable depuis l'onglet « E-mails » (administrateur). Cela
permet de faire fonctionner toute la démonstration — confirmation
d'identité, notification de décision — sans dépendre d'un vrai compte de
messagerie, tout en gardant le même code pour un déploiement réel.

L'envoi est toujours « best effort » : une erreur SMTP est consignée mais
ne remonte jamais à l'appelant (une panne de messagerie ne doit jamais
empêcher une inscription, une connexion ou une décision du DPO).
"""
from __future__ import annotations

import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from sqlalchemy.orm import Session

from app.config import (
    NOM_ETABLISSEMENT, SMTP_EXPEDITEUR, SMTP_HOTE, SMTP_MOT_DE_PASSE, SMTP_PORT,
    SMTP_TLS, SMTP_UTILISATEUR,
)
from app.models import EmailEnvoye

PIED_DE_PAGE = (
    "\n\n--\n"
    f"{NOM_ETABLISSEMENT} · Portail d'accès aux données de santé\n"
    "Ceci est un message automatique, merci de ne pas y répondre."
)


def _smtp_configure() -> bool:
    return bool(SMTP_HOTE)


def _envoyer_reellement(destinataire: str, sujet: str, corps: str,
                         piece_jointe: tuple[str, bytes] | None) -> None:
    message = MIMEMultipart()
    message["From"] = SMTP_EXPEDITEUR
    message["To"] = destinataire
    message["Subject"] = sujet
    message.attach(MIMEText(corps, "plain", "utf-8"))
    if piece_jointe is not None:
        nom_fichier, contenu = piece_jointe
        pj = MIMEApplication(contenu, Name=nom_fichier)
        pj["Content-Disposition"] = f'attachment; filename="{nom_fichier}"'
        message.attach(pj)

    with smtplib.SMTP(SMTP_HOTE, SMTP_PORT, timeout=10) as serveur:
        if SMTP_TLS:
            serveur.starttls()
        if SMTP_UTILISATEUR:
            serveur.login(SMTP_UTILISATEUR, SMTP_MOT_DE_PASSE)
        serveur.sendmail(SMTP_EXPEDITEUR, [destinataire], message.as_string())


def envoyer(db: Session, destinataire: str, sujet: str, corps: str, *,
            type_notification: str = "", piece_jointe: tuple[str, bytes] | None = None
            ) -> EmailEnvoye:
    """Rédige, consigne et (si possible) envoie un e-mail. Ne lève jamais."""
    trace = EmailEnvoye(
        destinataire=destinataire, sujet=sujet, corps=corps,
        type_notification=type_notification,
        piece_jointe_nom=piece_jointe[0] if piece_jointe else "",
        statut="SIMULE",
    )
    if _smtp_configure():
        try:
            _envoyer_reellement(destinataire, sujet, corps + PIED_DE_PAGE, piece_jointe)
            trace.statut = "ENVOYE"
        except Exception as erreur:  # noqa: BLE001 - l'envoi ne doit jamais bloquer l'appelant
            trace.statut = "ECHEC"
            trace.erreur = str(erreur)[:500]
    db.add(trace)
    db.flush()
    return trace


# ------------------------------------------------------------------ messages


def bienvenue(db: Session, destinataire: str, nom_complet: str) -> EmailEnvoye:
    sujet = f"{NOM_ETABLISSEMENT} — Confirmation de création de compte"
    corps = (
        f"Bonjour {nom_complet},\n\n"
        f"Votre compte sur le portail d'accès aux données de santé de {NOM_ETABLISSEMENT} "
        "vient d'être créé avec cette adresse e-mail.\n\n"
        "Si vous n'êtes pas à l'origine de cette création, contactez sans délai le "
        "délégué à la protection des données de l'établissement."
    )
    return envoyer(db, destinataire, sujet, corps, type_notification="CREATION_COMPTE")


def connexion(db: Session, destinataire: str, nom_complet: str, horodatage: str) -> EmailEnvoye:
    sujet = f"{NOM_ETABLISSEMENT} — Nouvelle connexion à votre compte"
    corps = (
        f"Bonjour {nom_complet},\n\n"
        f"Une connexion à votre compte vient d'avoir lieu le {horodatage}.\n\n"
        "Si ce n'est pas vous, modifiez votre mot de passe et contactez le délégué à "
        "la protection des données de l'établissement."
    )
    return envoyer(db, destinataire, sujet, corps, type_notification="CONNEXION")


def demande_acceptee(db: Session, destinataire: str, nom_complet: str, reference: str,
                      titre_projet: str, date_fin: str,
                      attestation: tuple[str, bytes] | None = None) -> EmailEnvoye:
    sujet = f"{NOM_ETABLISSEMENT} — Demande {reference} acceptée"
    corps = (
        f"Bonjour {nom_complet},\n\n"
        f"Votre demande d'accès « {titre_projet} » (référence {reference}) a été "
        f"acceptée par le délégué à la protection des données.\n"
        f"L'accès aux données est ouvert jusqu'au {date_fin}.\n\n"
        "Vous pouvez dès maintenant consulter et extraire les données depuis le "
        "portail. L'attestation d'autorisation est jointe à ce message."
    )
    return envoyer(db, destinataire, sujet, corps, type_notification="DEMANDE_ACCEPTEE",
                   piece_jointe=attestation)


def demande_refusee(db: Session, destinataire: str, nom_complet: str, reference: str,
                     titre_projet: str, motif: str) -> EmailEnvoye:
    sujet = f"{NOM_ETABLISSEMENT} — Demande {reference} refusée"
    corps = (
        f"Bonjour {nom_complet},\n\n"
        f"Votre demande d'accès « {titre_projet} » (référence {reference}) n'a pas "
        f"été acceptée par le délégué à la protection des données.\n\n"
        f"Motif communiqué : {motif}\n\n"
        "Vous pouvez déposer une nouvelle demande en tenant compte de ce motif."
    )
    return envoyer(db, destinataire, sujet, corps, type_notification="DEMANDE_REFUSEE")
