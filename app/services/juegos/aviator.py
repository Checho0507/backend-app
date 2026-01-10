from __future__ import annotations

from datetime import datetime, timedelta
import decimal
import random
import uuid
from typing import Dict, List, TypedDict, Optional
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ...api.juegos import game_sessions
from ...models import usuario
from ...database import get_db
from ...api.auth import get_current_user

router = APIRouter()

# ----------------------------------------------------------------------
# Configuración de Aviator - CORREGIDA
# ----------------------------------------------------------------------

APUESTAS_PERMITIDAS = [Decimal(str(x)) for x in [100, 500, 1000, 2000, 5000]]
MIN_MULTIPLICADOR = Decimal('1.0')
MAX_MULTIPLICADOR = Decimal('500.0')
MAX_HORAS_SESION = 1

# Probabilidades configuradas (más realistas)
PROBABILIDADES = [
    (Decimal('1.0'), Decimal('50.0')),       # 25% - crash inmediato en 1.0x
    (Decimal('1.5'), Decimal('30.0')),       # 25% - hasta 1.5x
    (Decimal('2.0'), Decimal('10.0')),       # 20% - hasta 2.0x
    (Decimal('5.0'), Decimal('5.0')),       # 15% - hasta 5.0x
    (Decimal('10.0'), Decimal('4.0')),       # 8% - hasta 10x
    (Decimal('50.0'), Decimal('0.9')),       # 4% - hasta 50x
    (Decimal('100.0'), Decimal('0.09')),      # 1% - hasta 100x
    (Decimal('200.0'), Decimal('0.007')),      # 0.07% - hasta 200x
    (Decimal('300.0'), Decimal('0.002')),      # 0.02% - hasta 300x
    (Decimal('500.0'), Decimal('0.001')),      # 0.01% - hasta 500x
]

# ----------------------------------------------------------------------
# Modelos in-memory
# ----------------------------------------------------------------------

class SesionAviator(TypedDict):
    user_id: int
    apuesta: Decimal
    multiplicador_crash: Decimal
    multiplicador_retiro: Optional[Decimal]
    retiro_manual: bool
    estado: str
    multiplicador_actual: Decimal
    auto_retiro_activo: bool
    multiplicador_auto: Decimal
    created_at: datetime
    tiempo_inicio: datetime
    tiempo_explosion: Optional[datetime]
    duracion_total: float


# ----------------------------------------------------------------------
# Utilidades de juego - CORREGIDAS
# ----------------------------------------------------------------------

def calcular_duracion_animacion(multiplicador: Decimal) -> Decimal:
    """
    Calcula la duración de la animación en segundos basado en el multiplicador.
    Retorna valores entre 0.5s y 30s máximo (no 60s para mejor experiencia).
    """
    if multiplicador <= Decimal('1.0'):
        return Decimal('0.5')
    
    # Para multiplicadores entre 1.0 y 1.5: muy rápido (0.5s a 1.5s)
    if multiplicador <= Decimal('1.5'):
        duracion = Decimal('0.5') + (multiplicador - Decimal('1.0')) * Decimal('2.0')
        return max(Decimal('0.5'), min(duracion.quantize(Decimal('0.1')), Decimal('30.0')))
    
    # Para multiplicadores entre 1.5 y 2.0: rápido (1.5s a 2.5s)
    if multiplicador <= Decimal('2.0'):
        duracion = Decimal('1.5') + (multiplicador - Decimal('1.5')) * Decimal('2.0')
        return max(Decimal('0.5'), min(duracion.quantize(Decimal('0.1')), Decimal('30.0')))
    
    # Para multiplicadores entre 2.0 y 10.0: medio (2.5s a 8s)
    if multiplicador <= Decimal('10.0'):
        duracion = Decimal('2.5') + (multiplicador - Decimal('2.0')) * Decimal('0.69')
        return max(Decimal('0.5'), min(duracion.quantize(Decimal('0.1')), Decimal('30.0')))
    
    # Para multiplicadores entre 10.0 y 100.0: lento (8s a 20s)
    if multiplicador <= Decimal('100.0'):
        duracion = Decimal('8.0') + (multiplicador - Decimal('10.0')) * Decimal('0.133')
        return max(Decimal('0.5'), min(duracion.quantize(Decimal('0.1')), Decimal('30.0')))
    
    # Para multiplicadores entre 100.0 y 500.0: muy lento (20s a 30s)
    if multiplicador <= Decimal('500.0'):
        duracion = Decimal('20.0') + (multiplicador - Decimal('100.0')) * Decimal('0.025')
        return max(Decimal('0.5'), min(duracion, Decimal('30.0'))).quantize(Decimal('0.1'))
    
    return Decimal('30.0')


def generar_multiplicador_crash() -> Decimal:
    """
    Genera un multiplicador de crash según las probabilidades especificadas.
    """
    r = random.random() * 100  # Porcentaje de 0 a 100
    
    acumulado = Decimal('0.0')
    for i, (multiplier, prob) in enumerate(PROBABILIDADES):
        acumulado += prob
        
        if r < float(acumulado):
            # Estamos en este rango
            if i == 0:
                # Crash inmediato en 1x
                return Decimal('1.00')
            
            min_val = PROBABILIDADES[i-1][0] if i > 0 else Decimal('1.0')
            max_val = multiplier
            
            # Generar valor aleatorio dentro del rango
            # Sesgo hacia valores bajos (más realista)
            u = random.random()
            factor = u ** 1.5  # Sesgo hacia valores bajos
            
            if min_val == max_val:
                return min_val
            
            resultado = min_val + (max_val - min_val) * Decimal(str(factor))
            # Asegurar que el resultado esté dentro de límites razonables
            resultado = max(MIN_MULTIPLICADOR, min(resultado, MAX_MULTIPLICADOR))
            return resultado.quantize(Decimal('0.01'))
    
    # Fallback seguro
    return Decimal('1.50')


def calcular_multiplicador_actual(
    tiempo_transcurrido: float,
    multiplicador_crash: Decimal,
    duracion_total: float
) -> Decimal:
    """
    Calcula el multiplicador actual basado en el tiempo transcurrido.
    Usa curva exponencial suave (easeOutQuad) para crecimiento natural.
    """
    if duracion_total <= 0:
        return Decimal('1.0')
    
    # Calcular progreso (0.0 a 1.0)
    progreso = min(tiempo_transcurrido / duracion_total, 1.0)
    
    # Aplicar función de easing (easeOutCubic para crecimiento suave)
    # Crece rápido al inicio, se desacelera al final
    progreso_eased = 1 - pow(1 - progreso, 3)
    
    # Calcular multiplicador: de 1.0 al multiplicador_crash
    rango = multiplicador_crash - Decimal('1.0')
    multiplicador = Decimal('1.0') + rango * Decimal(str(progreso_eased))
    
    # Asegurar que el multiplicador esté dentro de límites
    multiplicador = max(Decimal('1.0'), min(multiplicador, multiplicador_crash))
    
    return multiplicador.quantize(Decimal('0.01'))


def limpiar_sesiones_expiradas() -> None:
    """Elimina sesiones expiradas."""
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
    sesion: SesionAviator = game_sessions[session_id]
    if sesion["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="No tienes acceso a esta sesión")
    return sesion

# ----------------------------------------------------------------------
# Endpoints utilitarios
# ----------------------------------------------------------------------

@router.get("/juegos/aviator/apuestas-permitidas")
def leer_apuestas_permitidas():
    """Devuelve la lista de apuestas válidas para el front."""
    return {"apuestas_permitidas": [float(ap) for ap in APUESTAS_PERMITIDAS]}


@router.get("/juegos/aviator/historial")
def obtener_historial(
    limite: int = Query(20, description="Número de resultados a devolver", ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: usuario.Usuario = Depends(get_current_user),
):
    """Obtiene el historial de resultados recientes (público)."""
    historial = []
    now = datetime.now()
    
    for i in range(limite):
        multiplicador = generar_multiplicador_crash()
        timestamp = now - timedelta(seconds=i * random.randint(5, 15))
        
        # Determinar color basado en multiplicador
        if multiplicador < Decimal('1.5'):
            color = 'red'
        elif multiplicador < Decimal('2.0'):
            color = 'orange'
        elif multiplicador < Decimal('5.0'):
            color = 'yellow'
        elif multiplicador < Decimal('10.0'):
            color = 'green'
        else:
            color = 'purple'
        
        historial.append({
            "id": i + 1,
            "multiplicador": float(multiplicador),
            "timestamp": timestamp.isoformat(),
            "color": color
        })
    
    return {"historial": historial}

# ----------------------------------------------------------------------
# Iniciar vuelo - CORREGIDO
# ----------------------------------------------------------------------

@router.post("/juegos/aviator/iniciar")
def iniciar_vuelo(
    apuesta: Decimal = Query(
        ...,
        description="Monto de la apuesta",
        ge=Decimal('1.0'),
    ),
    db: Session = Depends(get_db),
    current_user: usuario.Usuario = Depends(get_current_user),
):
    """Inicia un nuevo vuelo."""
    limpiar_sesiones_expiradas()

    if apuesta not in APUESTAS_PERMITIDAS:
        raise HTTPException(
            status_code=400,
            detail=f"Apuesta no válida. Debe ser una de {[float(a) for a in APUESTAS_PERMITIDAS]}",
        )

    user = db.query(usuario.Usuario).filter(usuario.Usuario.id == current_user.id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if user.saldo < apuesta:
        raise HTTPException(status_code=400, detail=f"Saldo insuficiente. Necesitas ${apuesta} para jugar.")

    # Generar multiplicador de crash
    multiplicador_crash = generar_multiplicador_crash()
    
    # Calcular duración total de la animación
    duracion_total = float(calcular_duracion_animacion(multiplicador_crash))
    
    # Validar valores para evitar datos corruptos
    if not isinstance(multiplicador_crash, Decimal) or multiplicador_crash <= Decimal('0'):
        multiplicador_crash = Decimal('2.0')
    
    if not isinstance(duracion_total, (int, float)) or duracion_total <= 0:
        duracion_total = 5.0
    
    # Crear sesión
    session_id = str(uuid.uuid4())
    ahora = datetime.now()
    
    game_sessions[session_id] = {
        "user_id": user.id,
        "apuesta": apuesta,
        "multiplicador_crash": multiplicador_crash,
        "multiplicador_retiro": None,
        "retiro_manual": False,
        "estado": "vuelo",
        "multiplicador_actual": Decimal('1.0'),
        "auto_retiro_activo": False,
        "multiplicador_auto": Decimal('2.0'),
        "duracion_total": float(duracion_total),
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
        "apuesta": float(apuesta),
        "multiplicador_inicial": 1.0,
        "nuevo_saldo": float(user.saldo),
        "tiempo_inicio": ahora.isoformat(),
        "duracion_total": float(duracion_total),
        "multiplicador_crash": float(multiplicador_crash),
    }


# ----------------------------------------------------------------------
# Retirar (Cashout) - CORREGIDO
# ----------------------------------------------------------------------

@router.post("/juegos/aviator/{session_id}/cashout")
def hacer_cashout(
    session_id: str,
    multiplicador_actual: Decimal = Query(
        ...,
        description="Multiplicador actual en el momento del cashout",
        ge=Decimal('1.0'),
        le=Decimal('500.0'),
    ),
    db: Session = Depends(get_db),
    current_user: usuario.Usuario = Depends(get_current_user),
):
    """El jugador retira sus ganancias antes del crash."""
    limpiar_sesiones_expiradas()

    sesion = obtener_sesion_asegurada(session_id, current_user.id)
    
    if sesion["estado"] != "vuelo":
        raise HTTPException(status_code=400, detail="Este vuelo ya terminó")

    user = db.query(usuario.Usuario).filter(usuario.Usuario.id == current_user.id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    # Validar multiplicador_actual
    if not isinstance(multiplicador_actual, Decimal):
        multiplicador_actual = Decimal('1.0')
    
    # Verificar si ya pasó el crash point (con pequeño margen de tolerancia)
    margen = Decimal('0.05')
    if multiplicador_actual > sesion["multiplicador_crash"] + margen:
        # Ya explotó, el usuario perdió
        sesion["estado"] = "explosion"
        sesion["multiplicador_retiro"] = None
        sesion["retiro_manual"] = False
        sesion["tiempo_explosion"] = datetime.now()
        
        return {
            "resultado": f"¡CRASH! El avión explotó en {sesion['multiplicador_crash']}x",
            "ganancia": 0.0,
            "multiplicador_crash": float(sesion["multiplicador_crash"]),
            "multiplicador_retiro": None,
            "nuevo_saldo": float(user.saldo),
            "estado": "explosion"
        }

    # Calcular ganancia con el multiplicador actual
    # Limitar al multiplicador de crash si está muy cerca
    multiplicador_final = min(multiplicador_actual, sesion["multiplicador_crash"])
    
    # Validar multiplicador_final
    if multiplicador_final < Decimal('1.0'):
        multiplicador_final = Decimal('1.0')
    
    ganancia = sesion["apuesta"] * multiplicador_final
    
    # Actualizar sesión
    sesion["estado"] = "cashout"
    sesion["multiplicador_retiro"] = multiplicador_final
    sesion["retiro_manual"] = True
    sesion["multiplicador_actual"] = multiplicador_final
    sesion["tiempo_explosion"] = datetime.now()
    
    # Pagar al jugador
    user.saldo += ganancia
    db.commit()
    db.refresh(user)

    return {
        "resultado": f"¡Retiro exitoso! Ganaste ${float(ganancia):.2f}",
        "ganancia": float(ganancia),
        "multiplicador_crash": float(sesion["multiplicador_crash"]),
        "multiplicador_retiro": float(multiplicador_final),
        "nuevo_saldo": float(user.saldo),
        "estado": "cashout"
    }


# ----------------------------------------------------------------------
# Verificar estado del vuelo - CORREGIDO
# ----------------------------------------------------------------------

@router.get("/juegos/aviator/{session_id}/estado")
def verificar_estado(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: usuario.Usuario = Depends(get_current_user),
):
    """Verifica el estado actual del vuelo."""
    limpiar_sesiones_expiradas()

    sesion = obtener_sesion_asegurada(session_id, current_user.id)
    
    tiempo_transcurrido = (datetime.now() - sesion["tiempo_inicio"]).total_seconds()
    duracion_total = sesion.get("duracion_total", 30.0)
    
    # Validar duración total
    if duracion_total <= 0:
        duracion_total = 30.0
    
    multiplicador_actual = calcular_multiplicador_actual(
        tiempo_transcurrido, 
        sesion["multiplicador_crash"],
        duracion_total
    )
    
    # Verificar si ya explotó
    exploto = tiempo_transcurrido >= duracion_total or multiplicador_actual >= sesion["multiplicador_crash"]
    
    if exploto and sesion["estado"] == "vuelo":
        # Acaba de explotar
        sesion["estado"] = "explosion"
        sesion["tiempo_explosion"] = datetime.now()
    
    # Actualizar multiplicador actual en sesión
    sesion["multiplicador_actual"] = multiplicador_actual
    
    # Verificar retiro automático si está activo
    if (sesion["estado"] == "vuelo" and 
        sesion["auto_retiro_activo"] and 
        multiplicador_actual >= sesion["multiplicador_auto"] and
        sesion["multiplicador_auto"] <= sesion["multiplicador_crash"]):
        
        # Ejecutar retiro automático
        user = db.query(usuario.Usuario).filter(usuario.Usuario.id == current_user.id).first()
        if user:
            ganancia = sesion["apuesta"] * sesion["multiplicador_auto"]
            user.saldo += ganancia
            db.commit()
            db.refresh(user)
            
            sesion["estado"] = "cashout"
            sesion["multiplicador_retiro"] = sesion["multiplicador_auto"]
            sesion["retiro_manual"] = False
            sesion["tiempo_explosion"] = datetime.now()
            
            return {
                "session_id": session_id,
                "estado": "cashout",
                "multiplicador_actual": float(multiplicador_actual),
                "multiplicador_crash": float(sesion["multiplicador_crash"]),
                "multiplicador_retiro": float(sesion["multiplicador_auto"]),
                "apuesta": float(sesion["apuesta"]),
                "tiempo_transcurrido": tiempo_transcurrido,
                "exploto": False,
                "ganancia": float(ganancia),
                "nuevo_saldo": float(user.saldo),
                "auto_retiro": True,
            }
    
    return {
        "session_id": session_id,
        "estado": sesion["estado"],
        "multiplicador_actual": float(multiplicador_actual),
        "multiplicador_crash": float(sesion["multiplicador_crash"]) if sesion["estado"] != "vuelo" else None,
        "multiplicador_retiro": float(sesion["multiplicador_retiro"]) if sesion["multiplicador_retiro"] else None,
        "apuesta": float(sesion["apuesta"]),
        "tiempo_transcurrido": tiempo_transcurrido,
        "exploto": exploto,
        "duracion_total": duracion_total,
    }


# ----------------------------------------------------------------------
# Configurar Auto-retiro - CORREGIDO
# ----------------------------------------------------------------------

@router.post("/juegos/aviator/{session_id}/configurar-autoretiro")
def configurar_autoretiro(
    session_id: str,
    multiplicador_auto: Decimal = Query(
        ...,
        description="Multiplicador para retiro automático",
        ge=Decimal('1.1'),
        le=Decimal('500.0'),
    ),
    activar: bool = Query(True, description="Activar o desactivar auto-retiro"),
    db: Session = Depends(get_db),
    current_user: usuario.Usuario = Depends(get_current_user),
):
    """Configura retiro automático."""
    sesion = obtener_sesion_asegurada(session_id, current_user.id)
    
    if sesion["estado"] != "vuelo":
        raise HTTPException(status_code=400, detail="Este vuelo ya terminó")
    
    # Validar multiplicador_auto
    if multiplicador_auto < Decimal('1.1'):
        multiplicador_auto = Decimal('1.1')
    elif multiplicador_auto > Decimal('500.0'):
        multiplicador_auto = Decimal('500.0')
    
    sesion["auto_retiro_activo"] = activar
    sesion["multiplicador_auto"] = multiplicador_auto
    
    return {
        "mensaje": f"Retiro automático {'activado' if activar else 'desactivado'} en {multiplicador_auto}x",
        "multiplicador_auto": float(multiplicador_auto),
        "activado": activar
    }


# ----------------------------------------------------------------------
# Estadísticas del jugador
# ----------------------------------------------------------------------

@router.get("/juegos/aviator/estadisticas")
def obtener_estadisticas(
    db: Session = Depends(get_db),
    current_user: usuario.Usuario = Depends(get_current_user),
):
    """Obtiene estadísticas del jugador en Aviator."""
    # En un sistema real, esto vendría de la base de datos
    return {
        "total_vuelos": 0,
        "vuelos_ganados": 0,
        "vuelos_perdidos": 0,
        "ganancia_total": 0.0,
        "perdida_total": 0.0,
        "balance": 0.0,
        "mayor_ganancia": 0.0,
        "multiplicador_record": 0.0,
    }