from fastapi import APIRouter, FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from ..models import usuario
from ..database import get_db
from ..api.auth import get_current_user
from ..schemas.usuario import ReferidoOut

router = APIRouter()

# ========================
# SISTEMA DE REFERIDOS
# ========================
@router.get("/referidos", response_model=List[ReferidoOut])
def obtener_referidos(
    db: Session = Depends(get_db), 
    current_user: usuario.Usuario = Depends(get_current_user)
):
    """Obtener lista de usuarios referidos y ganancias"""
    referidos = db.query(usuario.Usuario).filter(
        usuario.Usuario.referido_por == current_user.id
    ).all()

    resultado = []

    for ref in referidos:
        # Ganancia base por referido
        ganancia_base = 2000 if ref.verificado else 100

        # Buscar subreferidos (referidos del referido)
        subreferidos = db.query(usuario.Usuario).filter(
            usuario.Usuario.referido_por == ref.id
        ).all()

        # Calcular ganancia por subreferidos (10% de ganancia)
        ganancia_subreferidos = 0
        for sub in subreferidos:
            sub_ganancia = 2000 if sub.verificado else 100
            ganancia_subreferidos += int(sub_ganancia * 0.10)

        resultado.append({
            "username": ref.username,
            "verificado": ref.verificado,
            "ganancia": ganancia_base + ganancia_subreferidos,
            "referidos": [
                {"username": sub.username, "verificado": sub.verificado}
                for sub in subreferidos
            ]
        })

    return resultado