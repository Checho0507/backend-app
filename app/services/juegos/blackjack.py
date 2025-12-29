# app/services/juegos/blackjack.py
from __future__ import annotations

from datetime import datetime, timedelta
import random
import uuid
from typing import Dict, List, TypedDict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

# Importa el almacén de sesiones COMPARTIDO
# Asegúrate de que en app/api/juegos.py exista:
#   game_sessions: Dict[str, dict] = {}
from ...api.juegos import game_sessions

# Dependencias del proyecto
from ...models import usuario
from ...database import get_db
from ...api.auth import get_current_user


router = APIRouter()

# ----------------------------------------------------------------------
# Configuración de Blackjack
# ----------------------------------------------------------------------

APUESTAS_PERMITIDAS = [100, 500, 1000, 2000, 5000]  # Deben coincidir con el front
MAX_HORAS_SESION = 1  # Limpieza de sesiones expiradas


# ----------------------------------------------------------------------
# Modelos in-memory (cartas y sesión)
# ----------------------------------------------------------------------

class Carta:
    """Representa una carta estándar para el Blackjack."""
    __slots__ = ("nombre", "palo", "valor")

    def __init__(self, nombre: str, palo: str, valor: int):
        self.nombre = nombre
        self.palo = palo
        self.valor = valor


class SesionBlackjack(TypedDict):
    user_id: int
    baraja: List[Carta]
    mano_jugador: List[Carta]
    mano_banca: List[Carta]
    apuesta: int
    created_at: datetime
    estado: str  # 'jugando' | 'terminado'


# ----------------------------------------------------------------------
# Utilidades de juego
# ----------------------------------------------------------------------

def crear_baraja() -> List[Carta]:
    """
    Crea una baraja de 52 cartas (1 mazo), barajada aleatoriamente.
    A=11 (ajustable), J/Q/K=10, resto valor nominal.
    """
    palos = ["♠️", "♥️", "♦️", "♣️"]
    nombres_valores = [
        ("A", 11), ("2", 2), ("3", 3), ("4", 4), ("5", 5), ("6", 6),
        ("7", 7), ("8", 8), ("9", 9), ("10", 10), ("J", 10), ("Q", 10), ("K", 10),
    ]
    baraja = [Carta(n, p, v) for p in palos for (n, v) in nombres_valores]
    random.shuffle(baraja)
    return baraja


def calcular_puntaje(mano: List[Carta]) -> int:
    """
    Suma valores, contando Ases como 11 y rebajando a 1 (resta 10) cuando sea necesario para no pasar de 21.
    """
    puntaje = 0
    ases = 0
    for c in mano:
        if c.nombre == "A":
            ases += 1
            puntaje += 11
        else:
            puntaje += c.valor

    while puntaje > 21 and ases > 0:
        puntaje -= 10
        ases -= 1
    return puntaje


def tiene_blackjack(mano: List[Carta]) -> bool:
    """True si la mano tiene exactamente 21 con 2 cartas."""
    return len(mano) == 2 and calcular_puntaje(mano) == 21


def carta_dict(c: Carta) -> dict:
    """Serializa una carta a dict para respuesta JSON."""
    return {"nombre": c.nombre, "palo": c.palo, "valor": c.valor}


def mano_dict(mano: List[Carta]) -> List[dict]:
    return [carta_dict(c) for c in mano]


def limpiar_sesiones_expiradas() -> None:
    """
    Elimina sesiones con más de MAX_HORAS_SESION de antigüedad.
    Debe llamarse en el inicio de cada endpoint del juego.
    """
    now = datetime.now()
    expiradas = []
    for sid, sdata in list(game_sessions.items()):
        created = sdata.get("created_at", now)
        if now - created > timedelta(hours=MAX_HORAS_SESION):
            expiradas.append(sid)
    for sid in expiradas:
        del game_sessions[sid]


def obtener_sesion_asegurada(session_id: str, user_id: int) -> SesionBlackjack:
    """Obtiene la sesión y valida existencia/propiedad/estado."""
    if session_id not in game_sessions:
        raise HTTPException(status_code=404, detail="Sesión de juego no encontrada")
    sesion: SesionBlackjack = game_sessions[session_id]  # type: ignore
    if sesion["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="No tienes acceso a esta sesión")
    if sesion["estado"] != "jugando":
        raise HTTPException(status_code=400, detail="El juego ya terminó")
    return sesion


# ----------------------------------------------------------------------
# Endpoints utilitarios (consumidos por el front)
# ----------------------------------------------------------------------

@router.get("/juegos/blackjack/apuestas-permitidas")
def leer_apuestas_permitidas():
    """
    Devuelve la lista de apuestas válidas para el front.
    Tu front ya consulta este endpoint en el useEffect.
    """
    return {"apuestas_permitidas": APUESTAS_PERMITIDAS}


# ----------------------------------------------------------------------
# Iniciar partida
# ----------------------------------------------------------------------

@router.post("/juegos/blackjack/iniciar")
def iniciar_blackjack(
    apuesta: int = Query(
        ...,
        description="Monto de la apuesta (100, 500, 1000, 2000, 5000)",
        ge=1,
    ),
    db: Session = Depends(get_db),
    current_user: usuario.Usuario = Depends(get_current_user),
):
    """
    Inicia una nueva sesión de Blackjack:
      - Valida apuesta y saldo
      - Resta la apuesta al usuario
      - Reparte 2 cartas jugador y banca
      - Guarda sesión (con apuesta) y retorna datos iniciales
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

    session_id = str(uuid.uuid4())
    baraja = crear_baraja()

    mano_jugador = [baraja.pop(), baraja.pop()]
    mano_banca = [baraja.pop(), baraja.pop()]

    puntaje_jugador = calcular_puntaje(mano_jugador)

    # Descontar apuesta
    user.saldo -= apuesta
    db.commit()
    db.refresh(user)

    # Persistimos la sesión en memoria
    game_sessions[session_id] = {
        "user_id": user.id,
        "baraja": baraja,
        "mano_jugador": mano_jugador,
        "mano_banca": mano_banca,
        "apuesta": apuesta,
        "created_at": datetime.now(),
        "estado": "jugando",
    }

    # Nota: el front muestra solo la primera carta de la banca
    puntaje_banca_visible = mano_banca[0].valor if mano_banca[0].nombre != "A" else 11

    return {
        "session_id": session_id,
        "mano_jugador": mano_dict(mano_jugador),
        "mano_banca": mano_dict(mano_banca),
        "puntaje_jugador": puntaje_jugador,
        "puntaje_banca_visible": puntaje_banca_visible,
        "nuevo_saldo": user.saldo,
        "jugador_blackjack": tiene_blackjack(mano_jugador),
    }


# ----------------------------------------------------------------------
# Pedir carta
# ----------------------------------------------------------------------

@router.post("/juegos/blackjack/{session_id}/pedir-carta")
def pedir_carta_blackjack(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: usuario.Usuario = Depends(get_current_user),
):
    """
    El jugador pide una carta:
      - Valida sesión/estado
      - Extrae 1 carta y recalcula puntaje
      - Si supera 21, termina (pierde) y se elimina la sesión
    """
    limpiar_sesiones_expiradas()

    sesion = obtener_sesion_asegurada(session_id, current_user.id)

    if not sesion["baraja"]:
        raise HTTPException(status_code=400, detail="No quedan cartas en la baraja")

    nueva_carta = sesion["baraja"].pop()
    sesion["mano_jugador"].append(nueva_carta)

    puntaje_jugador = calcular_puntaje(sesion["mano_jugador"])
    jugador_se_paso = puntaje_jugador > 21

    response = {
        "mano_jugador": mano_dict(sesion["mano_jugador"]),
        "puntaje_jugador": puntaje_jugador,
        "jugador_se_paso": jugador_se_paso,
    }

    if jugador_se_paso:
        # Fin de juego: no hay devolución, pierde su apuesta
        sesion["estado"] = "terminado"

        user = db.query(usuario.Usuario).filter(usuario.Usuario.id == current_user.id).first()
        if not user:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")

        puntaje_banca_final = calcular_puntaje(sesion["mano_banca"])

        response.update(
            {
                "resultado": "Te pasaste de 21. Perdiste.",
                "ganancia": 0,
                "nuevo_saldo": user.saldo,
                "puntaje_banca_final": puntaje_banca_final,
                "mano_banca_final": mano_dict(sesion["mano_banca"]),
            }
        )

        # Elimina la sesión: terminó
        del game_sessions[session_id]

    return response


# ----------------------------------------------------------------------
# Plantarse (turno de banca y resolución)
# ----------------------------------------------------------------------

@router.post("/juegos/blackjack/{session_id}/plantarse")
def plantarse_blackjack(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: usuario.Usuario = Depends(get_current_user),
):
    """
    El jugador se planta:
      - La banca juega hasta 17
      - Se decide resultado con regla de blackjack/puntajes
      - Se paga 2.5x en Blackjack (apuesta * 2.5), 2x al ganar normal, 1x al empate
      - Se elimina la sesión
    """
    limpiar_sesiones_expiradas()

    sesion = obtener_sesion_asegurada(session_id, current_user.id)

    user = db.query(usuario.Usuario).filter(usuario.Usuario.id == current_user.id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    puntaje_jugador = calcular_puntaje(sesion["mano_jugador"])
    puntaje_banca = calcular_puntaje(sesion["mano_banca"])

    # Guardamos estado inicial de la banca para animación en el front
    mano_banca_inicial = list(sesion["mano_banca"])
    puntaje_banca_inicial = puntaje_banca

    # Banca pide hasta 17 o más
    while puntaje_banca < 17:
        if not sesion["baraja"]:
            break
        sesion["mano_banca"].append(sesion["baraja"].pop())
        puntaje_banca = calcular_puntaje(sesion["mano_banca"])

    jugador_tiene_bj = tiene_blackjack(sesion["mano_jugador"])
    banca_tenia_bj_inicial = tiene_blackjack(mano_banca_inicial)

    apuesta = sesion["apuesta"]
    ganancia: int = 0
    resultado: str

    if puntaje_banca > 21:
        if jugador_tiene_bj:
            resultado = "¡Blackjack! La banca se pasó. Ganaste."
            ganancia = int(apuesta * 2.5)
        else:
            resultado = "La banca se pasó. Ganaste."
            ganancia = apuesta * 2
    elif jugador_tiene_bj and banca_tenia_bj_inicial:
        resultado = "Empate con blackjack."
        ganancia = apuesta
    elif jugador_tiene_bj:
        resultado = "¡Blackjack! Ganaste."
        ganancia = int(apuesta * 2.5)
    elif banca_tenia_bj_inicial:
        resultado = "La banca tiene blackjack. Perdiste."
        ganancia = 0
    elif puntaje_jugador > puntaje_banca:
        resultado = "Ganaste."
        ganancia = apuesta * 2
    elif puntaje_jugador == puntaje_banca:
        resultado = "Empate."
        ganancia = apuesta
    else:
        resultado = "Perdiste."
        ganancia = 0

    # Pagar (o devolver) al jugador
    user.saldo += ganancia
    db.commit()
    db.refresh(user)

    sesion["estado"] = "terminado"

    respuesta = {
        "resultado": resultado,
        "ganancia": ganancia,
        "nuevo_saldo": user.saldo,
        "mano_banca_inicial": mano_dict(mano_banca_inicial),
        "puntaje_banca_inicial": puntaje_banca_inicial,
        "mano_banca_final": mano_dict(sesion["mano_banca"]),
        "puntaje_banca_final": puntaje_banca,
        "puntaje_jugador_final": puntaje_jugador,
    }

    # Elimina la sesión: terminó
    del game_sessions[session_id]

    return respuesta


# ----------------------------------------------------------------------
# Notas:
# - La apuesta llega como query param: /juegos/blackjack/iniciar?apuesta=1000
# - El front ya usa 'apuestas-permitidas' y 'puntaje_banca_visible'
# - Las ganancias siempre se calculan con la apuesta guardada en sesión
# - Si deseas múltiples mazos, duplica crear_baraja() o ajusta su tamaño
# ----------------------------------------------------------------------
