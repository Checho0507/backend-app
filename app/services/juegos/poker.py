from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
import random
import uuid
from typing import Dict, List, Tuple, Optional
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ...api.juegos import game_sessions
from ...models import usuario
from ...database import get_db
from ...api.auth import get_current_user

router = APIRouter()

# ----------------------------------------------------------------------
# Configuración de Póker
# ----------------------------------------------------------------------

APUESTAS_PERMITIDAS = [200, 500, 1000, 2500, 5000, 10000]
BLINDS = [10, 25, 50, 100, 200, 500]
MAX_HORAS_SESION = 2


# ----------------------------------------------------------------------
# Enums y estructuras
# ----------------------------------------------------------------------

class Palo(Enum):
    CORAZONES = "♥️"
    DIAMANTES = "♦️"
    TREBOLES = "♣️"
    PICAS = "♠️"


class ValorCarta(Enum):
    DOS = ("2", 2)
    TRES = ("3", 3)
    CUATRO = ("4", 4)
    CINCO = ("5", 5)
    SEIS = ("6", 6)
    SIETE = ("7", 7)
    OCHO = ("8", 8)
    NUEVE = ("9", 9)
    DIEZ = ("10", 10)
    JOTA = ("J", 11)
    REINA = ("Q", 12)
    REY = ("K", 13)
    AS = ("A", 14)


class AccionJugador(Enum):
    PASAR = "pasar"
    IGUALAR = "igualar"
    SUBIR = "subir"
    RETIRARSE = "retirarse"


class ManoPoker(Enum):
    ESCALERA_REAL = 10
    ESCALERA_COLOR = 9
    POKER = 8
    FULL_HOUSE = 7
    COLOR = 6
    ESCALERA = 5
    TRIO = 4
    DOBLE_PAR = 3
    PAR = 2
    CARTA_ALTA = 1


class EstadoPartida(Enum):
    PRE_FLOP = "pre_flop"
    FLOP = "flop"
    TURN = "turn"
    RIVER = "river"
    SHOWDOWN = "showdown"
    TERMINADA = "terminada"


# ----------------------------------------------------------------------
# Modelos
# ----------------------------------------------------------------------

class CartaPoker:
    __slots__ = ("valor", "palo")

    def __init__(self, valor: ValorCarta, palo: Palo):
        self.valor = valor
        self.palo = palo

    def __repr__(self):
        return f"{self.valor.value[0]}{self.palo.value}"

    def valor_numerico(self) -> int:
        return self.valor.value[1]

    def nombre(self) -> str:
        return self.valor.value[0]


class JugadorPoker:
    __slots__ = ("usuario_id", "cartas", "fichas", "esta_en_juego", "ultima_accion", "fichas_iniciales")

    def __init__(self, usuario_id: int, fichas_iniciales: int):
        self.usuario_id = usuario_id
        self.cartas: List[CartaPoker] = []
        self.fichas = fichas_iniciales
        self.fichas_iniciales = fichas_iniciales
        self.esta_en_juego = True
        self.ultima_accion: Optional[str] = None

    def recibir_cartas(self, cartas: List[CartaPoker]):
        self.cartas = cartas

    def retirar(self):
        self.esta_en_juego = False
        self.ultima_accion = "retirarse"

    def puede_jugar(self) -> bool:
        return self.esta_en_juego

    def pagar(self, cantidad: int) -> bool:
        if cantidad < 0:
            return False
        if cantidad > self.fichas:
            return False
        self.fichas -= cantidad
        return True

    def total_apostado(self) -> int:
        return self.fichas_iniciales - self.fichas


class MesaPoker:
    __slots__ = (
        "cartas_comunitarias",
        "bote",
        "ronda_actual",
        "small_blind",
        "big_blind",
        # apuestas por calle
        "current_bet",
        "bets",  # [jugador, banca] lo puesto en ESTA calle
        # control 1 acción por ronda
        "jugador_actuo_en_calle",
        "banca_actuo_en_calle",
    )

    def __init__(self, small_blind: int = 10):
        self.cartas_comunitarias: List[CartaPoker] = []
        self.bote = 0
        self.ronda_actual = EstadoPartida.PRE_FLOP
        self.small_blind = small_blind
        self.big_blind = small_blind * 2

        self.current_bet = 0
        self.bets = [0, 0]  # 0 jugador, 1 banca

        self.jugador_actuo_en_calle = False
        self.banca_actuo_en_calle = False

    def reset_calle(self):
        self.current_bet = 0
        self.bets = [0, 0]
        self.jugador_actuo_en_calle = False
        self.banca_actuo_en_calle = False

    def to_call(self, idx: int) -> int:
        return max(0, self.current_bet - self.bets[idx])

    def meter_al_bote(self, cantidad: int):
        self.bote += cantidad


class SesionPoker:
    __slots__ = ("session_id", "mesa", "baraja", "usuario_id", "apuesta_inicial", "created_at", "estado", "banca_id", "jugador", "banca")

    def __init__(self, session_id: str, usuario_id: int, apuesta: int, blind: int, banca_id: int = 0):
        self.session_id = session_id
        self.usuario_id = usuario_id
        self.apuesta_inicial = apuesta
        self.created_at = datetime.now()
        self.estado = "activa"
        self.banca_id = banca_id

        self.mesa = MesaPoker(small_blind=blind)
        self.baraja = self.crear_baraja()
        random.shuffle(self.baraja)

        self.jugador = JugadorPoker(usuario_id, apuesta)
        self.banca = JugadorPoker(banca_id, apuesta * 2)

        self.repartir_cartas_privadas()
        self.procesar_blinds()

    def crear_baraja(self) -> List[CartaPoker]:
        return [CartaPoker(valor, palo) for palo in Palo for valor in ValorCarta]

    def repartir_cartas_privadas(self):
        self.jugador.recibir_cartas([self.baraja.pop(), self.baraja.pop()])
        self.banca.recibir_cartas([self.baraja.pop(), self.baraja.pop()])

    def procesar_blinds(self):
        # Heads-up simplificado: banca paga BB, jugador no paga SB (si quieres, aquí puedes cobrar SB también)
        bb = min(self.mesa.big_blind, self.banca.fichas)
        if not self.banca.pagar(bb):
            bb = 0
        self.mesa.bets[1] += bb
        self.mesa.meter_al_bote(bb)
        self.mesa.current_bet = bb

    def repartir_comunitarias(self, n: int):
        for _ in range(n):
            self.mesa.cartas_comunitarias.append(self.baraja.pop())

    # -------- Evaluación mano (tu lógica, con pequeños ajustes) --------

    def evaluar_mano(self, cartas: List[CartaPoker]) -> Tuple[ManoPoker, List[int]]:
        valores = sorted([c.valor_numerico() for c in cartas], reverse=True)
        palos = [c.palo for c in cartas]

        conteo_palos: Dict[Palo, int] = {}
        for p in palos:
            conteo_palos[p] = conteo_palos.get(p, 0) + 1

        conteo_valores: Dict[int, int] = {}
        for v in valores:
            conteo_valores[v] = conteo_valores.get(v, 0) + 1

        valores_ordenados = sorted(conteo_valores.items(), key=lambda x: (x[1], x[0]), reverse=True)

        # Escalera real
        valores_especiales = {10, 11, 12, 13, 14}
        for palo in Palo:
            vals = {c.valor_numerico() for c in cartas if c.palo == palo}
            if valores_especiales.issubset(vals):
                return ManoPoker.ESCALERA_REAL, [14, 13, 12, 11, 10]

        # Color (flush) candidate
        flush_palo = None
        for p, cnt in conteo_palos.items():
            if cnt >= 5:
                flush_palo = p
                break

        # Escalera (con As bajo)
        def hay_escalera(valset: List[int]) -> Optional[List[int]]:
            u = sorted(set(valset), reverse=True)
            for i in range(len(u) - 4):
                if u[i] - u[i + 4] == 4:
                    return u[i:i+5]
            if 14 in u:
                u2 = [x for x in u if x != 14] + [1]
                u2 = sorted(set(u2), reverse=True)
                for i in range(len(u2) - 4):
                    if u2[i] - u2[i + 4] == 4:
                        return u2[i:i+5]
            return None

        # Escalera color
        if flush_palo is not None:
            vals_flush = [c.valor_numerico() for c in cartas if c.palo == flush_palo]
            straight_flush = hay_escalera(vals_flush)
            if straight_flush:
                return ManoPoker.ESCALERA_COLOR, straight_flush

        # Poker
        if any(cnt == 4 for cnt in conteo_valores.values()):
            v4 = max(v for v, cnt in conteo_valores.items() if cnt == 4)
            kicker = max(v for v in valores if v != v4)
            return ManoPoker.POKER, [v4, kicker]

        # Full house
        if len(valores_ordenados) >= 2 and valores_ordenados[0][1] >= 3 and valores_ordenados[1][1] >= 2:
            return ManoPoker.FULL_HOUSE, [valores_ordenados[0][0], valores_ordenados[1][0]]

        # Color
        if flush_palo is not None:
            vals_flush = sorted([c.valor_numerico() for c in cartas if c.palo == flush_palo], reverse=True)
            return ManoPoker.COLOR, vals_flush[:5]

        # Escalera
        straight = hay_escalera(valores)
        if straight:
            return ManoPoker.ESCALERA, straight

        # Trio
        if any(cnt == 3 for cnt in conteo_valores.values()):
            v3 = max(v for v, cnt in conteo_valores.items() if cnt == 3)
            kickers = sorted([v for v in valores if v != v3], reverse=True)[:2]
            return ManoPoker.TRIO, [v3] + kickers

        # Pares
        pares = sorted([v for v, cnt in conteo_valores.items() if cnt == 2], reverse=True)
        if len(pares) >= 2:
            kicker = max(v for v in valores if v not in pares[:2])
            return ManoPoker.DOBLE_PAR, pares[:2] + [kicker]
        if len(pares) == 1:
            p = pares[0]
            kickers = sorted([v for v in valores if v != p], reverse=True)[:3]
            return ManoPoker.PAR, [p] + kickers

        return ManoPoker.CARTA_ALTA, valores[:5]


# ----------------------------------------------------------------------
# Utilidades
# ----------------------------------------------------------------------

def limpiar_sesiones_expiradas():
    now = datetime.now()
    expiradas = []
    for sid, sdata in list(game_sessions.items()):
        if isinstance(sdata, SesionPoker):
            if now - sdata.created_at > timedelta(hours=MAX_HORAS_SESION):
                expiradas.append(sid)
        else:
            created = sdata.get("created_at", now)
            if now - created > timedelta(hours=MAX_HORAS_SESION):
                expiradas.append(sid)
    for sid in expiradas:
        del game_sessions[sid]


def obtener_sesion_poker(session_id: str, user_id: int) -> SesionPoker:
    if session_id not in game_sessions:
        raise HTTPException(status_code=404, detail="Sesión de póker no encontrada")
    sesion = game_sessions[session_id]
    if not isinstance(sesion, SesionPoker):
        raise HTTPException(status_code=400, detail="ID de sesión inválido")
    if sesion.usuario_id != user_id:
        raise HTTPException(status_code=403, detail="No tienes acceso a esta sesión")
    return sesion


def carta_a_dict(carta: CartaPoker) -> dict:
    return {"valor": carta.nombre(), "palo": carta.palo.value, "valor_numerico": carta.valor_numerico()}


def nombre_mano(m: ManoPoker) -> str:
    return m.name.replace("_", " ").title()


# ----------------------------------------------------------------------
# Endpoints
# ----------------------------------------------------------------------

@router.get("/juegos/poker/apuestas-permitidas")
def leer_apuestas_permitidas():
    return {"apuestas_permitidas": APUESTAS_PERMITIDAS}


@router.get("/juegos/poker/blinds")
def leer_blinds():
    return {"blinds_disponibles": BLINDS}


@router.post("/juegos/poker/iniciar")
def iniciar_poker(
    apuesta: int = Query(..., description="Buy-in inicial", ge=1),
    blind: int = Query(25, description="Tamaño del blind pequeño"),
    db: Session = Depends(get_db),
    current_user: usuario.Usuario = Depends(get_current_user),
):
    limpiar_sesiones_expiradas()

    if apuesta not in APUESTAS_PERMITIDAS:
        raise HTTPException(status_code=400, detail=f"Apuesta no válida. Debe ser una de {APUESTAS_PERMITIDAS}")

    if blind not in BLINDS:
        raise HTTPException(status_code=400, detail=f"Blind no válido. Debe ser uno de {BLINDS}")

    user = db.query(usuario.Usuario).filter(usuario.Usuario.id == current_user.id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if user.saldo < apuesta:
        raise HTTPException(status_code=400, detail=f"Saldo insuficiente. Necesitas ${apuesta} para jugar.")

    user.saldo -= Decimal(apuesta)
    db.commit()
    db.refresh(user)

    session_id = str(uuid.uuid4())
    sesion = SesionPoker(session_id, user.id, apuesta, blind=blind)

    game_sessions[session_id] = sesion

    return {
        "session_id": session_id,
        "cartas_jugador": [carta_a_dict(c) for c in sesion.jugador.cartas],
        "fichas_jugador": sesion.jugador.fichas,
        "fichas_banca": sesion.banca.fichas,
        "bote": sesion.mesa.bote,
        "apuesta_minima": sesion.mesa.to_call(0),  # lo que te falta para igualar
        "ronda_actual": sesion.mesa.ronda_actual.value,
        "small_blind": sesion.mesa.small_blind,
        "big_blind": sesion.mesa.big_blind,
        "nuevo_saldo": user.saldo,
        "cartas_comunitarias": [],
        "estado": sesion.mesa.ronda_actual.value,
    }


def _avanzar_calle(s: SesionPoker):
    if s.mesa.ronda_actual == EstadoPartida.PRE_FLOP:
        s.mesa.ronda_actual = EstadoPartida.FLOP
        s.repartir_comunitarias(3)
    elif s.mesa.ronda_actual == EstadoPartida.FLOP:
        s.mesa.ronda_actual = EstadoPartida.TURN
        s.repartir_comunitarias(1)
    elif s.mesa.ronda_actual == EstadoPartida.TURN:
        s.mesa.ronda_actual = EstadoPartida.RIVER
        s.repartir_comunitarias(1)
    elif s.mesa.ronda_actual == EstadoPartida.RIVER:
        s.mesa.ronda_actual = EstadoPartida.SHOWDOWN

    s.mesa.reset_calle()


def _resolver_showdown(s: SesionPoker, db: Session, user: usuario.Usuario):
    mano_j, vals_j = s.evaluar_mano(s.jugador.cartas + s.mesa.cartas_comunitarias)
    mano_b, vals_b = s.evaluar_mano(s.banca.cartas + s.mesa.cartas_comunitarias)

    resultado = ""
    ganancia = 0

    if mano_j.value > mano_b.value:
        resultado = f"¡Ganaste con {nombre_mano(mano_j)}!"
        ganancia = s.mesa.bote - s.jugador.total_apostado()
        if ganancia > 0:
            user.saldo += Decimal(ganancia)
    elif mano_b.value > mano_j.value:
        resultado = f"La banca gana con {nombre_mano(mano_b)}."
        ganancia = -s.jugador.total_apostado()
    else:
        # desempate por kickers
        ganador = None
        for vj, vb in zip(vals_j, vals_b):
            if vj > vb:
                ganador = "jugador"
                break
            if vb > vj:
                ganador = "banca"
                break

        if ganador == "jugador":
            resultado = f"¡Ganaste con {nombre_mano(mano_j)} (carta más alta)!"
            ganancia = s.mesa.bote - s.jugador.total_apostado()
            if ganancia > 0:
                user.saldo += Decimal(ganancia)
        elif ganador == "banca":
            resultado = f"La banca gana con {nombre_mano(mano_b)} (carta más alta)."
            ganancia = -s.jugador.total_apostado()
        else:
            resultado = "¡Empate! El bote se divide."
            mitad = s.mesa.bote // 2
            ganancia = mitad - s.jugador.total_apostado()
            if ganancia > 0:
                user.saldo += Decimal(ganancia)

    db.commit()
    db.refresh(user)

    bote_final = s.mesa.bote
    s.mesa.bote = 0
    s.estado = "terminada"

    del game_sessions[s.session_id]

    return {
        "resultado": resultado,
        "ganancia": ganancia,
        "nuevo_saldo": user.saldo,
        "bote_final": bote_final,
        "estado": "terminada",
        "cartas_banca": [carta_a_dict(c) for c in s.banca.cartas],
        "cartas_comunitarias": [carta_a_dict(c) for c in s.mesa.cartas_comunitarias],
        "mano_jugador": nombre_mano(mano_j),
        "mano_banca": nombre_mano(mano_b),
    }


def _accion_banca(s: SesionPoker):
    # banca solo actúa una vez por calle
    if s.mesa.banca_actuo_en_calle or not s.banca.puede_jugar():
        return "espera", 0

    idx_b = 1
    to_call = s.mesa.to_call(idx_b)

    # fuerza aproximada con cartas visibles (privadas + comunitarias)
    mano_b, _ = s.evaluar_mano(s.banca.cartas + s.mesa.cartas_comunitarias)
    fuerza = mano_b.value

    accion = "pasar"
    cantidad_total_aporte = 0

    if to_call == 0:
        # puede pasar o apostar (subir desde 0)
        if fuerza >= ManoPoker.PAR.value and random.random() < 0.45:
            # apuesta "razonable"
            raise_amount = max(s.mesa.big_blind, 10)
            raise_amount = min(raise_amount, s.banca.fichas)
            if raise_amount > 0:
                s.banca.pagar(raise_amount)
                s.mesa.bets[idx_b] += raise_amount
                s.mesa.current_bet = max(s.mesa.current_bet, s.mesa.bets[idx_b])
                s.mesa.meter_al_bote(raise_amount)
                accion = "subir"
                cantidad_total_aporte = raise_amount
            else:
                accion = "pasar"
        else:
            accion = "pasar"
    else:
        # hay apuesta: igualar o subir (nunca se retira)
        if fuerza >= ManoPoker.PAR.value and random.random() < 0.35:
            # subir: paga to_call + raise_extra
            raise_extra = max(s.mesa.big_blind, to_call)  # sube al menos una ciega
            total = to_call + raise_extra
            total = min(total, s.banca.fichas)
            if total > 0:
                s.banca.pagar(total)
                s.mesa.bets[idx_b] += total
                s.mesa.current_bet = max(s.mesa.current_bet, s.mesa.bets[idx_b])
                s.mesa.meter_al_bote(total)
                accion = "subir"
                cantidad_total_aporte = total
            else:
                accion = "igualar"
        else:
            pago = min(to_call, s.banca.fichas)
            if pago > 0:
                s.banca.pagar(pago)
                s.mesa.bets[idx_b] += pago
                s.mesa.meter_al_bote(pago)
            accion = "igualar"
            cantidad_total_aporte = pago

    s.mesa.banca_actuo_en_calle = True
    s.banca.ultima_accion = accion
    return accion, cantidad_total_aporte


@router.post("/juegos/poker/{session_id}/accion")
def realizar_accion(
    session_id: str,
    accion: str = Query(..., description="Acción a realizar"),
    cantidad: int = Query(0, description="Cantidad total a aportar en la acción (para subir)"),
    db: Session = Depends(get_db),
    current_user: usuario.Usuario = Depends(get_current_user),
):
    limpiar_sesiones_expiradas()
    s = obtener_sesion_poker(session_id, current_user.id)

    user = db.query(usuario.Usuario).filter(usuario.Usuario.id == current_user.id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if s.estado == "terminada":
        raise HTTPException(status_code=400, detail="La partida ya terminó")

    if not s.jugador.puede_jugar():
        raise HTTPException(status_code=400, detail="El jugador ya se retiró")

    if s.mesa.jugador_actuo_en_calle:
        raise HTTPException(status_code=400, detail="Ya realizaste una acción en esta ronda")

    # normalizar acción
    try:
        a = AccionJugador(accion)
    except Exception:
        raise HTTPException(status_code=400, detail=f"Acción '{accion}' no válida")

    idx_j = 0
    to_call = s.mesa.to_call(idx_j)

    # ---- acción jugador (1 por calle) ----
    if a == AccionJugador.RETIRARSE:
        s.jugador.retirar()
        s.estado = "terminada"
        bote_final = s.mesa.bote
        s.mesa.bote = 0
        ganancia = -s.jugador.total_apostado()

        del game_sessions[session_id]
        return {
            "resultado": "Te retiraste. La banca gana el bote.",
            "ganancia": ganancia,
            "nuevo_saldo": user.saldo,
            "bote_final": bote_final,
            "estado": "terminada",
            "cartas_banca": [carta_a_dict(c) for c in s.banca.cartas],
            "cartas_comunitarias": [carta_a_dict(c) for c in s.mesa.cartas_comunitarias],
            "mano_jugador": "Retirarse",
            "mano_banca": "",
        }

    if a == AccionJugador.PASAR:
        if to_call != 0:
            raise HTTPException(status_code=400, detail="No puedes pasar: tienes una apuesta pendiente para igualar")
        s.jugador.ultima_accion = "pasar"
        s.mesa.jugador_actuo_en_calle = True

    elif a == AccionJugador.IGUALAR:
        if to_call <= 0:
            # ya está igualado => se considera pasar
            s.jugador.ultima_accion = "pasar"
            s.mesa.jugador_actuo_en_calle = True
        else:
            pago = min(to_call, s.jugador.fichas)
            if pago != to_call:
                raise HTTPException(status_code=400, detail="Fichas insuficientes para igualar")
            s.jugador.pagar(pago)
            s.mesa.bets[idx_j] += pago
            s.mesa.meter_al_bote(pago)
            s.jugador.ultima_accion = "igualar"
            s.mesa.jugador_actuo_en_calle = True

    elif a == AccionJugador.SUBIR:
        # cantidad = APORTE TOTAL del jugador en esta acción (incluye igualar + raise)
        # regla mínima: si hay apuesta, al menos to_call + big_blind; si no hay, al menos big_blind
        min_raise_total = (to_call + s.mesa.big_blind) if to_call > 0 else s.mesa.big_blind
        if cantidad < min_raise_total:
            raise HTTPException(status_code=400, detail=f"Subida mínima: {min_raise_total}")
        if cantidad > s.jugador.fichas:
            raise HTTPException(status_code=400, detail="Fichas insuficientes para esa subida")

        s.jugador.pagar(cantidad)
        s.mesa.bets[idx_j] += cantidad
        # el current_bet es lo máximo apostado en la calle (por cualquiera)
        s.mesa.current_bet = max(s.mesa.current_bet, s.mesa.bets[idx_j])
        s.mesa.meter_al_bote(cantidad)
        s.jugador.ultima_accion = "subir"
        s.mesa.jugador_actuo_en_calle = True

    # ---- acción banca (1 por calle) ----
    accion_banca, cantidad_banca = _accion_banca(s)

    # ---- si ambos actuaron, y están igualados => avanzar ----
    if s.mesa.jugador_actuo_en_calle and s.mesa.banca_actuo_en_calle:
        if s.mesa.bets[0] == s.mesa.bets[1]:
            _avanzar_calle(s)

    # showdown?
    if s.mesa.ronda_actual == EstadoPartida.SHOWDOWN:
        return _resolver_showdown(s, db, user)

    return {
        "fichas_jugador": s.jugador.fichas,
        "fichas_banca": s.banca.fichas,
        "bote": s.mesa.bote,
        "apuesta_minima": s.mesa.to_call(0),
        "ronda_actual": s.mesa.ronda_actual.value,
        "cartas_comunitarias": [carta_a_dict(c) for c in s.mesa.cartas_comunitarias],
        "accion_banca": f"{accion_banca} ({cantidad_banca})" if accion_banca in ["igualar", "subir"] else accion_banca,
        "estado": s.mesa.ronda_actual.value,
    }


@router.post("/juegos/poker/{session_id}/rendirse")
def rendirse(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: usuario.Usuario = Depends(get_current_user),
):
    limpiar_sesiones_expiradas()
    s = obtener_sesion_poker(session_id, current_user.id)

    user = db.query(usuario.Usuario).filter(usuario.Usuario.id == current_user.id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    total_apostado = s.jugador.total_apostado()

    if total_apostado == 0:
        devolucion = s.apuesta_inicial
        ganancia = 0
    else:
        devolucion = total_apostado // 2
        ganancia = devolucion - total_apostado

    user.saldo += Decimal(devolucion)
    db.commit()
    db.refresh(user)

    del game_sessions[session_id]

    return {
        "resultado": (
            f"Te rendiste. Recuperaste ${devolucion} de ${total_apostado} apostados."
            if total_apostado > 0
            else "Te rendiste antes de apostar. Recuperaste tu buy-in completo."
        ),
        "devolucion": devolucion,
        "ganancia": ganancia,
        "nuevo_saldo": user.saldo,
        "estado": "terminada",
    }


@router.get("/juegos/poker/{session_id}/estado")
def obtener_estado(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: usuario.Usuario = Depends(get_current_user),
):
    limpiar_sesiones_expiradas()
    s = obtener_sesion_poker(session_id, current_user.id)

    return {
        "session_id": session_id,
        "cartas_jugador": [carta_a_dict(c) for c in s.jugador.cartas],
        "fichas_jugador": s.jugador.fichas,
        "fichas_banca": s.banca.fichas,
        "bote": s.mesa.bote,
        "apuesta_minima": s.mesa.to_call(0),
        "ronda_actual": s.mesa.ronda_actual.value,
        "cartas_comunitarias": [carta_a_dict(c) for c in s.mesa.cartas_comunitarias],
        "estado": s.mesa.ronda_actual.value if s.estado != "terminada" else "terminada",
        "ultima_accion_jugador": s.jugador.ultima_accion,
        "ultima_accion_banca": s.banca.ultima_accion,
    }
