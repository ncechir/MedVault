from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import DATABASE_URL

# Les hébergeurs donnent souvent « postgres://… » : SQLAlchemy veut un pilote explicite.
_url = DATABASE_URL
if _url.startswith("postgres://"):
    _url = "postgresql+psycopg2://" + _url[len("postgres://"):]
elif _url.startswith("postgresql://"):
    _url = "postgresql+psycopg2://" + _url[len("postgresql://"):]

if _url.startswith("sqlite"):
    # SQLite : attend jusqu'à 30 s si la base est occupée
    engine = create_engine(_url, connect_args={"check_same_thread": False, "timeout": 30})
else:
    # PostgreSQL (base hébergée, qui survit aux redémarrages du site)
    engine = create_engine(_url, pool_pre_ping=True, pool_recycle=300)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """Dépendance FastAPI : ouvre une session par requête et la referme."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
