from fastapi import APIRouter, Depends

from app import config
from app.dependencies import utilisateur_courant
from app.schemas import ParametresOut

router = APIRouter(prefix="/parametres", tags=["Technique"],
                   dependencies=[Depends(utilisateur_courant)])


@router.get("", response_model=ParametresOut)
def lire():
    """Règles de gouvernance en vigueur, affichées telles quelles à l'écran."""
    return {
        "delai_preavis_jours": config.DELAI_PREAVIS_JOURS,
        "delai_purge_jours": config.DELAI_PURGE_JOURS,
        "duree_acces_max_mois": config.DUREE_ACCES_MAX_MOIS,
    }
