from fastapi import APIRouter, FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from datetime import date, datetime, timedelta
from ...models.usuario import Usuario
from ...database import get_db
from ...api.auth import get_current_user

router = APIRouter()

# Configuración de bonificaciones
BONUS_VERIFICADO = 500
BONUS_NO_VERIFICADO = 100

# ========================
# SISTEMA DE BONIFICACIONES
@router.post("/bonus-diario")
def reclamar_bonus_diario(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    """Reclamar bonus diario"""

    # Obtener usuario persistente en la sesión actual
    user = db.query(Usuario).filter(Usuario.id == current_user.id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    hoy = datetime.today()+timedelta(hours=-5)

    # Verificar si ya reclamó hoy
    if user.ultima_recompensa == hoy:
        raise HTTPException(
            status_code=400,
            detail="Ya reclamaste tu bonus diario hoy. Regresa mañana."
        )

    # Calcular monto según verificación
    monto_bonus = BONUS_VERIFICADO if user.verificado else BONUS_NO_VERIFICADO

    # Actualizar saldo y fecha
    user.saldo += monto_bonus
    user.ultima_recompensa = hoy

    db.commit()
    db.refresh(user)

    return {
        "mensaje": f"Bonus diario reclamado: +${monto_bonus}",
        "monto": monto_bonus,
        "nuevo_saldo": user.saldo,
        "tipo_usuario": "verificado" if user.verificado else "no_verificado"
    }

