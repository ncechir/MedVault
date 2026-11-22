from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import mailer
from app.audit import journaliser
from app.database import get_db
from app.dependencies import utilisateur_courant
from app.models import Role, Utilisateur, maintenant
from app.schemas import InscriptionIn, Token, UtilisateurOut
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


@router.get("/me", response_model=UtilisateurOut)
def moi(user: Utilisateur = Depends(utilisateur_courant)):
    return user
