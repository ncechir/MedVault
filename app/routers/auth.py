import base64
import binascii

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import mailer
from app.audit import journaliser
from app.database import get_db
from app.dependencies import utilisateur_courant
from app.models import Demande, Role, Utilisateur, maintenant
from app.schemas import (
    InscriptionIn, MotDePasseIn, PhotoIn, ProfilMaj, ProfilOut, Token,
)
from app.security import creer_token, hacher_mot_de_passe, verifier_mot_de_passe

router = APIRouter(prefix="/auth", tags=["Authentification"])


@router.post("/login", response_model=Token)
def login(
    form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
):
    email = form.username.strip().lower()
    user = db.scalar(select(Utilisateur).where(Utilisateur.email == email))
    if not user or not verifier_mot_de_passe(form.password, user.mot_de_passe_hash):
        journaliser(db, None, "CONNEXION_ECHOUEE", "utilisateur", details=form.username)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Identifiants incorrects",
        )
    if not user.actif:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Ce compte a été désactivé. Contactez un administrateur.",
        )
    journaliser(db, user, "CONNEXION", "utilisateur", user.id)
    mailer.connexion(db, user.email, user.nom_complet, maintenant().strftime("%d/%m/%Y %H:%M"))
    db.commit()
    return Token(access_token=creer_token(user.id, user.role.value))


@router.post("/inscription", response_model=Token, status_code=201)
def inscription(payload: InscriptionIn, db: Session = Depends(get_db)):
    """Création de compte libre, avec une adresse personnelle ou universitaire.

    Créer un compte ne donne accès à aucune donnée : le compte a toujours le rôle
    de simple demandeur, et chaque accès reste soumis à la décision du
    responsable des données. Les rôles de responsable et d'administrateur ne
    s'obtiennent jamais par ce formulaire.
    """
    if not payload.engagement:
        raise HTTPException(422, "L'engagement de confidentialité doit être accepté.")

    email = payload.email.strip().lower()
    if db.scalar(select(Utilisateur).where(Utilisateur.email == email)):
        raise HTTPException(409, "Un compte existe déjà avec cette adresse.")

    user = Utilisateur(
        email=email,
        nom_complet=payload.nom_complet.strip(),
        service=payload.service.strip(),
        role=Role.CHERCHEUR,
        mot_de_passe_hash=hacher_mot_de_passe(payload.mot_de_passe),
    )
    db.add(user)
    db.flush()
    journaliser(db, user, "COMPTE_CREE", "utilisateur", user.id, engagement=True)
    mailer.bienvenue(db, user.email, user.nom_complet)
    db.commit()
    return Token(access_token=creer_token(user.id, user.role.value))


def _profil(db: Session, user: Utilisateur) -> ProfilOut:
    nb = db.scalar(select(func.count(Demande.id)).where(Demande.demandeur_id == user.id)) or 0
    sortie = ProfilOut.model_validate(user)
    sortie.nb_demandes = nb
    return sortie


@router.get("/me", response_model=ProfilOut)
def moi(user: Utilisateur = Depends(utilisateur_courant), db: Session = Depends(get_db)):
    return _profil(db, user)


@router.put("/profil", response_model=ProfilOut)
def modifier_profil(
    payload: ProfilMaj,
    user: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
):
    """Nom et service : l'adresse e-mail et le rôle ne se changent pas ici."""
    user.nom_complet = payload.nom_complet.strip()
    user.service = payload.service.strip()
    journaliser(db, user, "PROFIL_MODIFIE", "utilisateur", user.id)
    db.commit()
    return _profil(db, user)


# Signatures des seuls formats acceptés : on contrôle les octets, pas seulement
# l'en-tête déclaré, et on refuse le SVG (qui peut embarquer du script).
_FORMATS_PHOTO = {
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/webp": (b"RIFF",),
}
TAILLE_PHOTO_MAX = 150_000  # octets, après décodage


@router.put("/photo", response_model=ProfilOut)
def definir_photo(
    payload: PhotoIn,
    user: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
):
    entete, _, donnees = payload.image.partition(",")
    if not entete.startswith("data:") or not entete.endswith(";base64"):
        raise HTTPException(422, "Image invalide.")
    type_mime = entete[5:-7]
    signatures = _FORMATS_PHOTO.get(type_mime)
    if not signatures:
        raise HTTPException(422, "Formats acceptés : PNG, JPEG ou WebP.")
    try:
        brut = base64.b64decode(donnees, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(422, "Image invalide.")
    if len(brut) > TAILLE_PHOTO_MAX:
        raise HTTPException(413, "Image trop lourde (150 Ko maximum).")
    if not brut.startswith(signatures):
        raise HTTPException(422, "Le contenu ne correspond pas au format annoncé.")
    user.photo = payload.image
    journaliser(db, user, "PHOTO_PROFIL_MODIFIEE", "utilisateur", user.id)
    db.commit()
    return _profil(db, user)


@router.delete("/photo", response_model=ProfilOut)
def supprimer_photo(
    user: Utilisateur = Depends(utilisateur_courant), db: Session = Depends(get_db),
):
    user.photo = None
    journaliser(db, user, "PHOTO_PROFIL_SUPPRIMEE", "utilisateur", user.id)
    db.commit()
    return _profil(db, user)


@router.post("/mot-de-passe", status_code=204)
def changer_mot_de_passe(
    payload: MotDePasseIn,
    user: Utilisateur = Depends(utilisateur_courant),
    db: Session = Depends(get_db),
):
    if not verifier_mot_de_passe(payload.actuel, user.mot_de_passe_hash):
        journaliser(db, user, "MOT_DE_PASSE_REFUSE", "utilisateur", user.id)
        db.commit()
        raise HTTPException(403, "Le mot de passe actuel est incorrect.")
    if payload.nouveau == payload.actuel:
        raise HTTPException(422, "Le nouveau mot de passe doit être différent de l'actuel.")
    user.mot_de_passe_hash = hacher_mot_de_passe(payload.nouveau)
    journaliser(db, user, "MOT_DE_PASSE_CHANGE", "utilisateur", user.id)
    db.commit()
