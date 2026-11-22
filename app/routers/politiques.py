"""Politiques de données réutilisables : règles de confidentialité appliquées
à toutes les extractions (seuil de k-anonymat, action, limite d'export)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import journaliser
from app.database import get_db
from app.dependencies import exiger_role
from app.models import PolitiqueDonnees, Role, Utilisateur
from app.schemas import PolitiqueIn, PolitiqueOut

router = APIRouter(prefix="/politiques", tags=["Politiques de données"])

DPO = exiger_role(Role.DPO)
LECTURE = exiger_role(Role.DPO, Role.ADMIN)


@router.get("", response_model=list[PolitiqueOut], dependencies=[Depends(LECTURE)])
def lister(db: Session = Depends(get_db)):
    return db.scalars(select(PolitiqueDonnees).order_by(
        PolitiqueDonnees.par_defaut.desc(), PolitiqueDonnees.nom)).all()


def _nom_libre(db: Session, nom: str, sauf_id: int | None = None) -> None:
    autre = db.scalar(select(PolitiqueDonnees).where(PolitiqueDonnees.nom == nom.strip()))
    if autre and autre.id != sauf_id:
        raise HTTPException(409, "Une politique porte déjà ce nom.")


@router.post("", response_model=PolitiqueOut, status_code=201)
def creer(corps: PolitiqueIn, db: Session = Depends(get_db),
          dpo: Utilisateur = Depends(DPO)):
    _nom_libre(db, corps.nom)
    premiere = db.scalar(select(PolitiqueDonnees.id).limit(1)) is None
    p = PolitiqueDonnees(
        nom=corps.nom.strip(), description=corps.description.strip(),
        k_min=corps.k_min, action=corps.action,
        max_lignes_export=corps.max_lignes_export,
        par_defaut=premiere, cree_par_id=dpo.id)
    db.add(p)
    db.flush()
    journaliser(db, dpo, "POLITIQUE_CREEE", "politique", p.id, nom=p.nom,
                k_min=p.k_min, regle=p.action)
    db.commit()
    db.refresh(p)
    return p


@router.put("/{politique_id}", response_model=PolitiqueOut)
def modifier(politique_id: int, corps: PolitiqueIn, db: Session = Depends(get_db),
             dpo: Utilisateur = Depends(DPO)):
    p = db.get(PolitiqueDonnees, politique_id)
    if not p:
        raise HTTPException(404, "Politique introuvable")
    _nom_libre(db, corps.nom, sauf_id=p.id)
    avant = {"k_min": p.k_min, "action": p.action, "max": p.max_lignes_export}
    p.nom, p.description = corps.nom.strip(), corps.description.strip()
    p.k_min, p.action, p.max_lignes_export = corps.k_min, corps.action, corps.max_lignes_export
    journaliser(db, dpo, "POLITIQUE_MODIFIEE", "politique", p.id, nom=p.nom,
                avant=avant, apres={"k_min": p.k_min, "action": p.action,
                                    "max": p.max_lignes_export})
    db.commit()
    db.refresh(p)
    return p


@router.post("/{politique_id}/defaut", response_model=PolitiqueOut)
def definir_par_defaut(politique_id: int, db: Session = Depends(get_db),
                       dpo: Utilisateur = Depends(DPO)):
    p = db.get(PolitiqueDonnees, politique_id)
    if not p:
        raise HTTPException(404, "Politique introuvable")
    for autre in db.scalars(select(PolitiqueDonnees)).all():
        autre.par_defaut = autre.id == p.id
    journaliser(db, dpo, "POLITIQUE_DEFAUT", "politique", p.id, nom=p.nom)
    db.commit()
    db.refresh(p)
    return p


@router.delete("/{politique_id}", status_code=204)
def supprimer(politique_id: int, db: Session = Depends(get_db),
              dpo: Utilisateur = Depends(DPO)):
    p = db.get(PolitiqueDonnees, politique_id)
    if not p:
        raise HTTPException(404, "Politique introuvable")
    if p.par_defaut:
        raise HTTPException(409, "La politique par défaut ne peut pas être supprimée : "
                                 "désignez-en d'abord une autre.")
    journaliser(db, dpo, "POLITIQUE_SUPPRIMEE", "politique", p.id, nom=p.nom)
    db.delete(p)
    db.commit()
    return None
