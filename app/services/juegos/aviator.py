from __future__ import annotations

from datetime import datetime, timedelta
import decimal
import random
import uuid
import math
from typing import Dict, List, TypedDict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

# Importa el almacén de sesiones COMPARTIDO
from ...api.juegos import game_sessions

# Dependencias del proyecto
from ...models import usuario
from ...database import get_db
from ...api.auth import get_current_user

router = APIRouter()

# ----------------------------------------------------------------------
# Configuración de Aviator
# ----------------------------------------------------------------------

APUESTAS_PERMITIDAS = [100, 500, 1000, 2000, 5000]
MIN_MULTIPLICADOR = 1.0
MAX_MULTIPLICADOR = 100.0
PROBABILIDAD_EXPLOSION_BAJA = 0.30# 30% de explotar antes de 1.5x
MAX_HORAS_SESION = 1

# ----------------------------------------------------------------------
# Modelos in-memory (sesión de Aviator)
# ----------------------------------------------------------------------

class SesionAviator(TypedDict):
    user_id: int
    apuesta: decimal.Decimal
    multiplicador_crash: decimal.Decimal  # Multiplicador en el que explotó/explotará
    multiplicador_retiro: Optional[decimal.Decimal]  # Multiplicador en el que el usuario retiró
    retiro_manual: bool
    estado: str  # 'vuelo' | 'cashout' | 'explosion'
    multiplicador_actual: decimal.Decimal
    created_at: datetime
    tiempo_inicio: datetime
    tiempo_explosion: Optional[datetime]


# ----------------------------------------------------------------------
# Utilidades de juego
# ----------------------------------------------------------------------

def generar_multiplicador_crash() -> decimal.Decimal:
    """
    Genera un multiplicador de crash usando distribución sesgada.
    Mayor probabilidad de números bajos, menor probabilidad de números altos.
    """
    # Usamos una distribución exponencial para que los crashes bajos sean más probables
    r = random.random()
    
    # 15% de probabilidad de crash entre 1.0 y 1.5
    if r < PROBABILIDAD_EXPLOSION_BAJA:
        return random.uniform(1.0, 1.5)
    
    # 85% restante: distribución que favorece números bajos pero permite altos
    # Función que da más peso a valores bajos
    u = random.random()
    
    # Transformación para obtener valores entre 1.5 y 100
    # Usamos una función exponencial inversa para hacer raros los valores altos
    if u < 0.7:  # 70% de crashes entre 1.5 y 3.0
        return random.uniform(1.5, 3.0)
    elif u < 0.9:  # 20% entre 3.0 y 10.0
        return random.uniform(3.0, 10.0)
    elif u < 0.98:  # 8% entre 10.0 y 30.0
        return random.uniform(10.0, 30.0)
    else:  # 2% entre 30.0 y 100.0
        return random.uniform(30.0, 100.0)


def calcular_multiplicador_actual(tiempo_transcurrido: decimal.Decimal, multiplicador_crash: decimal.Decimal) -> decimal.Decimal:
    """
    Calcula el multiplicador actual basado en el tiempo transcurrido.
    Curva exponencial que crece rápidamente al inicio y luego se ralentiza.
    """
    # Tiempo total estimado para llegar al crash (en segundos)
    # Ajustamos según el multiplicador_crash
    tiempo_total = (multiplicador_crash * 0.1)  # Más alto = más tiempo
    
    # Normalizamos el tiempo
    t = min(tiempo_transcurrido / tiempo_total, 1.0)
    
    # Curva suave: e^(t) - 1, normalizada para terminar en multiplicador_crash
    # Ajustamos para que comience más lento y acelere
    if t < 0.3:
        # Más lento al inicio
        progreso = (t / 0.3) ** 1.5
    else:
        # Más rápido después
        progreso = 0.3 ** 1.5 + ((t - 0.3) / 0.7) * (1 - 0.3 ** 1.5)
    
    # Multiplicador actual
    multiplicador = 1.0 + (multiplicador_crash - 1.0) * progreso
    
    return round(multiplicador, 2)


def limpiar_sesiones_expiradas() -> None:
    """Elimina sesiones con más de MAX_HORAS_SESION de antigüedad."""
    now = datetime.now()
    expiradas = []
    for sid, sdata in list(game_sessions.items()):
        created = sdata.get("created_at", now)
        if now - created > timedelta(hours=MAX_HORAS_SESION):
            expiradas.append(sid)
    for sid in expiradas:
        del game_sessions[sid]


def obtener_sesion_asegurada(session_id: str, user_id: int) -> SesionAviator:
    """Obtiene la sesión y valida existencia/propiedad."""
    if session_id not in game_sessions:
        raise HTTPException(status_code=404, detail="Sesión de juego no encontrada")
    sesion: SesionAviator = game_sessions[session_id]  # type: ignore
    if sesion["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="No tienes acceso a esta sesión")
    return sesion


# ----------------------------------------------------------------------
# Endpoints utilitarios
# ----------------------------------------------------------------------

@router.get("/juegos/aviator/apuestas-permitidas")
def leer_apuestas_permitidas():
    """Devuelve la lista de apuestas válidas para el front."""
    return {"apuestas_permitidas": APUESTAS_PERMITIDAS}


@router.get("/juegos/aviator/historial")
def obtener_historial(
    limite: int = Query(10, description="Número de resultados a devolver", ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: usuario.Usuario = Depends(get_current_user),
):
    """
    Obtiene el historial de resultados recientes (público).
    Esto muestra los crashes recientes para que los jugadores vean tendencias.
    """
    # En un sistema real, esto vendría de la base de datos
    # Por ahora, generamos algunos datos de ejemplo
    historial = []
    for i in range(limite):
        # Generar resultados realistas
        multiplicador = generar_multiplicador_crash()
        historial.append({
            "id": i + 1,
            "multiplicador": round(multiplicador, 2),
            "timestamp": (datetime.now() - timedelta(minutes=i*2)).isoformat(),
            "color": "green" if multiplicador > 3.0 else "orange" if multiplicador > 1.5 else "red"
        })
    
    return {"historial": historial}


# ----------------------------------------------------------------------
# Iniciar vuelo
# ----------------------------------------------------------------------

@router.post("/juegos/aviator/iniciar")
def iniciar_vuelo(
    apuesta: decimal.Decimal = Query(
        ...,
        description="Monto de la apuesta",
        ge=1,
    ),
    db: Session = Depends(get_db),
    current_user: usuario.Usuario = Depends(get_current_user),
):
    """
    Inicia un nuevo vuelo:
      - Valida apuesta y saldo
      - Resta la apuesta al usuario
      - Genera un multiplicador de crash aleatorio
      - Inicia sesión de vuelo
    """
    limpiar_sesiones_expiradas()

    if apuesta not in APUESTAS_PERMITIDAS:
        raise HTTPException(
            status_code=400,
            detail=f"Apuesta no válida. Debe ser una de {APUESTAS_PERMITIDAS}",
        )

    user = db.query(usuario.Usuario).filter(usuario.Usuario.id == current_user.id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if user.saldo < apuesta:
        raise HTTPException(status_code=400, detail=f"Saldo insuficiente. Necesitas ${apuesta} para jugar.")

    # Generar multiplicador de crash
    multiplicador_crash = generar_multiplicador_crash()
    
    # Calcular tiempo estimado de crash (en segundos)
    tiempo_estimado_crash = 2.0 + (multiplicador_crash * 0.1)
    
    # Crear sesión
    session_id = str(uuid.uuid4())
    ahora = datetime.now()
    
    game_sessions[session_id] = {
        "user_id": user.id,
        "apuesta": apuesta,
        "multiplicador_crash": multiplicador_crash,
        "multiplicador_retiro": None,
        "retiro_manual": False,
        "estado": "vuelo",  # 'vuelo', 'cashout', 'explosion'
        "multiplicador_actual": 1.0,
        "created_at": ahora,
        "tiempo_inicio": ahora,
        "tiempo_explosion": None,
    }

    # Descontar apuesta
    user.saldo -= apuesta
    db.commit()
    db.refresh(user)

    return {
        "session_id": session_id,
        "apuesta": apuesta,
        "multiplicador_inicial": 1.0,
        "nuevo_saldo": user.saldo,
        "tiempo_inicio": ahora.isoformat(),
        "tiempo_estimado_crash": tiempo_estimado_crash,  # Solo para referencia, no exacto
    }


# ----------------------------------------------------------------------
# Retirar (Cashout)
# ----------------------------------------------------------------------

@router.post("/juegos/aviator/{session_id}/cashout")
def hacer_cashout(
    session_id: str,
    multiplicador_actual: decimal.Decimal = Query(
        ...,
        description="Multiplicador actual en el momento del cashout (validación frontend)",
        ge=1.0,
    ),
    db: Session = Depends(get_db),
    current_user: usuario.Usuario = Depends(get_current_user),
):
    """
    El jugador retira sus ganancias antes del crash:
      - Valida que el vuelo esté activo
      - Calcula ganancia: apuesta * multiplicador_actual
      - Actualiza saldo
    """
    limpiar_sesiones_expiradas()

    sesion = obtener_sesion_asegurada(session_id, current_user.id)
    
    if sesion["estado"] != "vuelo":
        raise HTTPException(status_code=400, detail="Este vuelo ya terminó")

    user = db.query(usuario.Usuario).filter(usuario.Usuario.id == current_user.id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    # Validar que el multiplicador no haya superado el crash
    tiempo_transcurrido = (datetime.now() - sesion["tiempo_inicio"]).total_seconds()
    multiplicador_calculado = calcular_multiplicador_actual(tiempo_transcurrido, sesion["multiplicador_crash"])
    
    # Verificar si ya pasó el crash point
    if multiplicador_actual > sesion["multiplicador_crash"]:
        # Ya explotó, el usuario perdió
        sesion["estado"] = "explosion"
        sesion["multiplicador_retiro"] = None
        sesion["retiro_manual"] = False
        
        return {
            "resultado": "¡CRASH! El avión explotó antes de que pudieras retirar.",
            "ganancia": 0,
            "multiplicador_crash": sesion["multiplicador_crash"],
            "multiplicador_retiro": None,
            "nuevo_saldo": user.saldo,
            "estado": "explosion"
        }

    # Calcular ganancia
    ganancia = sesion["apuesta"] * multiplicador_actual
    
    # Actualizar sesión
    sesion["estado"] = "cashout"
    sesion["multiplicador_retiro"] = multiplicador_actual
    sesion["retiro_manual"] = True
    sesion["multiplicador_actual"] = multiplicador_actual
    
    # Pagar al jugador
    user.saldo += ganancia
    db.commit()
    db.refresh(user)

    return {
        "resultado": f"¡Retiro exitoso! Ganaste ${ganancia:.2f}",
        "ganancia": ganancia,
        "multiplicador_crash": sesion["multiplicador_crash"],
        "multiplicador_retiro": multiplicador_actual,
        "nuevo_saldo": user.saldo,
        "estado": "cashout"
    }


# ----------------------------------------------------------------------
# Verificar estado del vuelo
# ----------------------------------------------------------------------

@router.get("/juegos/aviator/{session_id}/estado")
def verificar_estado(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: usuario.Usuario = Depends(get_current_user),
):
    """
    Verifica el estado actual del vuelo:
      - Devuelve el multiplicador actual
      - Indica si ya explotó
      - Para actualizaciones en tiempo real
    """
    limpiar_sesiones_expiradas()

    sesion = obtener_sesion_asegurada(session_id, current_user.id)
    
    tiempo_transcurrido = (datetime.now() - sesion["tiempo_inicio"]).total_seconds()
    multiplicador_actual = calcular_multiplicador_actual(tiempo_transcurrido, sesion["multiplicador_crash"])
    
    # Verificar si ya explotó
    exploto = multiplicador_actual >= sesion["multiplicador_crash"]
    
    if exploto and sesion["estado"] == "vuelo":
        # Acaba de explotar
        sesion["estado"] = "explosion"
        sesion["tiempo_explosion"] = datetime.now()
        
        user = db.query(usuario.Usuario).filter(usuario.Usuario.id == current_user.id).first()
        if user:
            # El jugador pierde la apuesta (ya fue descontada al inicio)
            # No hay que hacer nada más
            pass
    
    # Actualizar multiplicador actual en sesión
    sesion["multiplicador_actual"] = multiplicador_actual
    
    return {
        "session_id": session_id,
        "estado": sesion["estado"],
        "multiplicador_actual": multiplicador_actual,
        "multiplicador_crash": sesion["multiplicador_crash"] if sesion["estado"] != "vuelo" else None,
        "multiplicador_retiro": sesion["multiplicador_retiro"],
        "apuesta": sesion["apuesta"],
        "tiempo_transcurrido": tiempo_transcurrido,
        "exploto": exploto,
    }


# ----------------------------------------------------------------------
# Auto-retiro (configuración de retiro automático)
# ----------------------------------------------------------------------

@router.post("/juegos/aviator/{session_id}/configurar-autoretiro")
def configurar_autoretiro(
    session_id: str,
    multiplicador_auto: decimal.Decimal = Query(
        ...,
        description="Multiplicador para retiro automático",
        ge=1.1,
        le=50.0,
    ),
    db: Session = Depends(get_db),
    current_user: usuario.Usuario = Depends(get_current_user),
):
    """
    Configura retiro automático en un multiplicador específico.
    """
    sesion = obtener_sesion_asegurada(session_id, current_user.id)
    
    if sesion["estado"] != "vuelo":
        raise HTTPException(status_code=400, detail="Este vuelo ya terminó")
    
    # En una implementación real, guardarías esta configuración
    # Por ahora, solo validamos
    return {
        "mensaje": f"Retiro automático configurado en {multiplicador_auto}x",
        "multiplicador_auto": multiplicador_auto
    }


# ----------------------------------------------------------------------
# Estadísticas del jugador
# ----------------------------------------------------------------------

@router.get("/juegos/aviator/estadisticas")
def obtener_estadisticas(
    db: Session = Depends(get_db),
    current_user: usuario.Usuario = Depends(get_current_user),
):
    """
    Obtiene estadísticas del jugador en Aviator.
    """
    # En un sistema real, esto vendría de la base de datos
    # Por ahora, retornamos datos de ejemplo
    return {
        "total_vuelos": 0,
        "vuelos_ganados": 0,
        "vuelos_perdidos": 0,
        "ganancia_total": 0,
        "perdida_total": 0,
        "balance": 0,
        "mayor_ganancia": 0,
        "multiplicador_record": 0,
    }