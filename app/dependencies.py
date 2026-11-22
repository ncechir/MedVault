from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Role, Utilisateur
from app.security import decoder_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def utilisateur_courant(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> Utilisateur:
    erreur = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentification invalide",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decoder_token(token)
        utilisateur_id = int(payload["sub"])
    except Exception:
        raise erreur

    utilisateur = db.get(Utilisateur, utilisateur_id)
    if utilisateur is None or not utilisateur.actif:
        raise erreur
    return utilisateur


def exiger_role(*roles: Role):
    """Fabrique de dépendance : restreint un endpoint à certains rôles."""

    def _verifier(user: Utilisateur = Depends(utilisateur_courant)) -> Utilisateur:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Action réservée aux rôles : "
                + ", ".join(r.value for r in roles),
            )
        return user

    return _verifier
