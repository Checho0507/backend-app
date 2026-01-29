from fastapi import APIRouter, FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime, timedelta
from ...models.usuario import Usuario
from ...database import get_db
from ...api.auth import get_current_user

router = APIRouter()

# Configuración de bonificaciones
BONUS_VERIFICADO = 100
BONUS_NO_VERIFICADO = 10

# ========================
# SISTEMA DE BONIFICACIONES
@router.post("/bonus-diario")
def reclamar_bonus_diario(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    """Reclamar bonus diario - Usando datetime con zona horaria Colombia"""

    # Obtener usuario persistente en la sesión actual
    user = db.query(Usuario).filter(Usuario.id == current_user.id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    # Obtener fecha y hora actual en UTC
    ahora_utc = datetime.today()
    
    # Ajustar a zona horaria de Colombia (UTC-5)
    # Nota: Colombia no tiene horario de verano, siempre es UTC-5
    colombia_offset = timedelta(hours=-5)
    ahora_colombia = ahora_utc + colombia_offset
    
    # Extraer solo la fecha (sin hora) para comparación
    hoy_colombia = ahora_colombia.date()
    
    # Verificar si ya reclamó hoy
    # Asegurarse de que ultima_recompensa sea date para comparar con date
    if user.ultima_recompensa and user.ultima_recompensa == hoy_colombia:
        raise HTTPException(
            status_code=400,
            detail=f"Ya reclamaste tu bonus diario hoy a las {user.ultima_hora_recompensa.strftime('%H:%M') if hasattr(user, 'ultima_hora_recompensa') else 'hoy'}. Regresa mañana."
        )
    
    # Calcular monto según verificación
    monto_bonus = BONUS_VERIFICADO if user.verificado else BONUS_NO_VERIFICADO
    
    # Actualizar saldo y fecha
    user.saldo += monto_bonus
    user.ultima_recompensa = hoy_colombia
    
    # Opcional: Guardar también la hora exacta del reclamo
    # Si tu modelo tiene campo para hora, descomenta estas líneas:
    # if hasattr(user, 'ultima_hora_recompensa'):
    #     user.ultima_hora_recompensa = ahora_colombia
    
    db.commit()
    db.refresh(user)

    return {
        "mensaje": f"✅ Bonus diario reclamado: +${monto_bonus} COP",
        "monto": monto_bonus,
        "nuevo_saldo": user.saldo,
        "tipo_usuario": "verificado" if user.verificado else "no_verificado",
        "fecha_reclamo": hoy_colombia.strftime("%d/%m/%Y"),
        "hora_reclamo": ahora_colombia.strftime("%H:%M:%S"),
        "proximo_disponible": "Mañana a partir de las 00:00 (hora Colombia)"
    }


# Opcional: Endpoint para verificar cuándo se puede reclamar nuevamente
@router.get("/bonus-diario/estado")
def estado_bonus_diario(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    """Verificar estado del bonus diario"""
    
    user = db.query(Usuario).filter(Usuario.id == current_user.id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    ahora_utc = datetime.utcnow()
    colombia_offset = timedelta(hours=-5)
    ahora_colombia = ahora_utc + colombia_offset
    hoy_colombia = ahora_colombia.date()
    
    # Calcular tiempo restante si ya reclamó hoy
    if user.ultima_recompensa and user.ultima_recompensa == hoy_colombia:
        # Calcular cuándo será disponible nuevamente (mañana a las 00:00 hora Colombia)
        manana = hoy_colombia + timedelta(days=1)
        tiempo_restante = "Disponible mañana"
        
        return {
            "puede_reclamar": False,
            "mensaje": "Ya reclamaste el bonus hoy",
            "ultimo_reclamo": user.ultima_recompensa.strftime("%d/%m/%Y"),
            "proximo_disponible": manana.strftime("%d/%m/%Y"),
            "tiempo_restante": tiempo_restante,
            "monto_proximo": BONUS_VERIFICADO if user.verificado else BONUS_NO_VERIFICADO
        }
    
    # Si no ha reclamado hoy
    monto_bonus = BONUS_VERIFICADO if user.verificado else BONUS_NO_VERIFICADO
    
    return {
        "puede_reclamar": True,
        "mensaje": f"Puedes reclamar ${monto_bonus} COP",
        "monto_disponible": monto_bonus,
        "tipo_usuario": "verificado" if user.verificado else "no_verificado",
        "hora_actual_colombia": ahora_colombia.strftime("%H:%M:%S"),
        "fecha_actual_colombia": hoy_colombia.strftime("%d/%m/%Y")
    }