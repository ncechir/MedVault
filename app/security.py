from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext

from app.config import ALGORITHM, DUREE_TOKEN_MINUTES, SECRET_KEY

# pbkdf2_sha256 : pur Python, pas de dépendance binaire à installer
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def hacher_mot_de_passe(mot_de_passe: str) -> str:
    return pwd_context.hash(mot_de_passe)


def verifier_mot_de_passe(clair: str, hache: str) -> bool:
    return pwd_context.verify(clair, hache)


def creer_token(utilisateur_id: int, role: str) -> str:
    payload = {
        "sub": str(utilisateur_id),
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=DUREE_TOKEN_MINUTES),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decoder_token(token: str) -> dict:
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
