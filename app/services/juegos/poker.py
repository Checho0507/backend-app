"""
Poker Texas Hold'em vs Banca — Rewrite completo.
Evaluación correcta de las 9 jugadas usando combinaciones C(7,5).
"""
from __future__ import annotations

import random
import uuid
from collections import Counter
from datetime import datetime, timedelta
from decimal import Decimal
from itertools import combinations
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ...api.juegos import game_sessions
from ...models import usuario
from ...database import get_db
from ...api.auth import get_current_user

router = APIRouter()

# ─────────────────────────── Configuración ────────────────────────────
APUESTAS_PERMITIDAS = [500, 1000, 2500, 5000, 10000]
BLINDS_DISPONIBLES  = [25, 50, 100, 200]
MAX_HORAS_SESION    = 2

# ─────────────────────────── Baraja ───────────────────────────────────
VALORES  = ["2","3","4","5","6","7","8","9","10","J","Q","K","A"]
NUM      = {"2":2,"3":3,"4":4,"5":5,"6":6,"7":7,"8":8,"9":9,"10":10,"J":11,"Q":12,"K":13,"A":14}
PALOS    = ["♠","♥","♦","♣"]
PALO_EMOJI = {"♠":"♠️","♥":"♥️","♦":"♦️","♣":"♣️"}

def _nueva_baraja() -> List[dict]:
    b = [{"v": v, "p": p, "n": NUM[v]} for p in PALOS for v in VALORES]
    random.shuffle(b)
    return b

def _c(c: dict) -> dict:
    """Convierte carta interna al formato JSON para el frontend."""
    return {"valor": c["v"], "palo": PALO_EMOJI[c["p"]], "valor_numerico": c["n"]}

# ─────────────────────────── Evaluador de mano ───────────────────────
# Rangos de mano (mayor = mejor)
CARTA_ALTA    = 1
PAR           = 2
DOBLE_PAR     = 3
TRIO          = 4
ESCALERA      = 5
COLOR         = 6
FULL_HOUSE    = 7
POKER_4       = 8
ESC_COLOR     = 9
ESC_REAL      = 10

NOMBRE = {
    CARTA_ALTA:  "Carta Alta",
    PAR:         "Par",
    DOBLE_PAR:   "Doble Par",
    TRIO:        "Trío",
    ESCALERA:    "Escalera",
    COLOR:       "Color",
    FULL_HOUSE:  "Full House",
    POKER_4:     "Póker (Cuatro Iguales)",
    ESC_COLOR:   "Escalera de Color",
    ESC_REAL:    "Escalera Real",
}

def _evaluar5(cartas: List[dict]) -> Tuple[int, List[int]]:
    """Evalúa EXACTAMENTE 5 cartas. Devuelve (rango, [desempate...])."""
    vals  = sorted([c["n"] for c in cartas], reverse=True)
    palos = [c["p"] for c in cartas]

    es_color   = len(set(palos)) == 1
    unicos     = sorted(set(vals), reverse=True)

    def _straight_top(vs: List[int]) -> Optional[int]:
        u = sorted(set(vs), reverse=True)
        for i in range(len(u) - 4):
            if u[i] - u[i+4] == 4:
                return u[i]
        # rueda A-2-3-4-5
        if 14 in u and {2,3,4,5}.issubset(set(u)):
            return 5
        return None

    top_str = _straight_top(vals)
    es_esc   = top_str is not None

    cnt    = Counter(vals)
    grupos = sorted(cnt.items(), key=lambda x: (x[1], x[0]), reverse=True)

    # Escalera Real
    if es_color and es_esc and set(vals) == {10,11,12,13,14}:
        return ESC_REAL, [14]

    # Escalera de Color
    if es_color and es_esc:
        return ESC_COLOR, [top_str]

    # Póker (cuatro iguales)
    if grupos[0][1] == 4:
        v4  = grupos[0][0]
        kik = max(v for v in vals if v != v4)
        return POKER_4, [v4, kik]

    # Full House
    if grupos[0][1] == 3 and len(grupos) >= 2 and grupos[1][1] >= 2:
        return FULL_HOUSE, [grupos[0][0], grupos[1][0]]

    # Color
    if es_color:
        return COLOR, vals[:5]

    # Escalera
    if es_esc:
        if top_str == 5 and 14 in vals:
            return ESCALERA, [5,4,3,2,1]
        return ESCALERA, [top_str, top_str-1, top_str-2, top_str-3, top_str-4]

    # Trío
    if grupos[0][1] == 3:
        v3   = grupos[0][0]
        kiks = sorted([v for v in vals if v != v3], reverse=True)[:2]
        return TRIO, [v3] + kiks

    # Doble Par
    pares = [v for v,c in cnt.items() if c == 2]
    if len(pares) >= 2:
        p1,p2 = sorted(pares, reverse=True)[:2]
        kik   = max(v for v in vals if v != p1 and v != p2)
        return DOBLE_PAR, [p1, p2, kik]

    # Par
    if len(pares) == 1:
        p    = pares[0]
        kiks = sorted([v for v in vals if v != p], reverse=True)[:3]
        return PAR, [p] + kiks

    # Carta Alta
    return CARTA_ALTA, vals[:5]


def mejor_mano(pool: List[dict]) -> Tuple[int, List[int]]:
    """Mejor mano posible de 5 cartas sacadas de `pool` (hasta 7)."""
    if len(pool) < 5:
        # todavía no hay suficientes cartas; evaluación parcial
        return _evaluar5(pool + [{"v":"2","p":"♠","n":2}] * (5 - len(pool)))
    mejor_r, mejor_t = -1, []
    for combo in combinations(pool, 5):
        r, t = _evaluar5(list(combo))
        if r > mejor_r or (r == mejor_r and t > mejor_t):
            mejor_r, mejor_t = r, t
    return mejor_r, mejor_t


# ─────────────────────────── Sesión de juego ─────────────────────────
class SesionPoker:
    def __init__(self, session_id: str, usuario_id: int, apuesta: int, blind: int):
        self.session_id  = session_id
        self.usuario_id  = usuario_id
        self.apuesta_ini = apuesta
        self.created_at  = datetime.now()

        self.blind     = blind          # small blind
        self.big_blind = blind * 2

        # Baraja y reparto
        self.baraja: List[dict] = _nueva_baraja()
        self.cartas_j: List[dict] = [self.baraja.pop(), self.baraja.pop()]
        self.cartas_b: List[dict] = [self.baraja.pop(), self.baraja.pop()]
        self.comun:    List[dict] = []

        # Fichas (cada uno con el buy-in)
        self.fichas_j = apuesta
        self.fichas_b = apuesta

        # Estado
        self.ronda = "pre_flop"          # pre_flop | flop | turn | river | showdown
        self.terminada = False

        # Apuestas de la calle actual
        self.bet_j    = 0   # lo que el jugador aportó esta calle
        self.bet_b    = 0
        self.nivel    = 0   # apuesta máxima vigente (to-call level)
        self.bote     = 0

        # ¿Quién ha actuado esta calle?
        self.actuo_j  = False
        self.actuo_b  = False

        # Última acción de la banca (para mostrar al jugador)
        self.ultima_acc_b = ""

        # Blinds: jugador = SB, banca = BB
        sb = min(blind, self.fichas_j)
        bb = min(self.big_blind, self.fichas_b)
        self.fichas_j -= sb
        self.fichas_b -= bb
        self.bet_j = sb
        self.bet_b = bb
        self.bote  = sb + bb
        self.nivel = bb   # para igualar el BB

    # ── Auxiliares ──────────────────────────────────────────────────
    def to_call_j(self) -> int:
        return max(0, self.nivel - self.bet_j)

    def to_call_b(self) -> int:
        return max(0, self.nivel - self.bet_b)

    def _reset_calle(self):
        self.bet_j   = 0
        self.bet_b   = 0
        self.nivel   = 0
        self.actuo_j = False
        self.actuo_b = False

    def _avanzar_ronda(self):
        self._reset_calle()
        orden = ["pre_flop","flop","turn","river","showdown"]
        idx = orden.index(self.ronda)
        self.ronda = orden[idx + 1]
        if self.ronda == "flop":
            self.comun += [self.baraja.pop(), self.baraja.pop(), self.baraja.pop()]
        elif self.ronda in ("turn", "river"):
            self.comun.append(self.baraja.pop())

    def _pagar_j(self, cantidad: int) -> int:
        pago = min(cantidad, self.fichas_j)
        self.fichas_j -= pago
        self.bet_j    += pago
        self.nivel     = max(self.nivel, self.bet_j)
        self.bote     += pago
        return pago

    def _pagar_b(self, cantidad: int) -> int:
        pago = min(cantidad, self.fichas_b)
        self.fichas_b -= pago
        self.bet_b    += pago
        self.nivel     = max(self.nivel, self.bet_b)
        self.bote     += pago
        return pago

    # ── IA de la banca ──────────────────────────────────────────────
    def _banca_actua(self):
        """
        Banca actúa una vez por calle.
        Estrategia: evalúa su mano actual y decide pasar/igualar/subir.
        Nunca se retira (es la casa).
        """
        pool_b = self.cartas_b + self.comun
        rango_b, _ = mejor_mano(pool_b) if pool_b else (CARTA_ALTA, [])

        tc = self.to_call_b()

        if tc == 0:
            # puede pasar o apostar
            if rango_b >= TRIO or (rango_b >= PAR and random.random() < 0.5):
                apuesta = max(self.big_blind, int(self.bote * 0.5))
                apuesta = min(apuesta, self.fichas_b)
                if apuesta > 0:
                    self._pagar_b(apuesta)
                    self.ultima_acc_b = f"Banca apuesta ${apuesta}"
                else:
                    self.ultima_acc_b = "Banca pasa"
            else:
                self.ultima_acc_b = "Banca pasa"
        else:
            # tiene que pagar para ver
            if rango_b >= DOBLE_PAR and random.random() < 0.4:
                # sube
                extra = max(self.big_blind, tc)
                total = tc + extra
                total = min(total, self.fichas_b)
                self._pagar_b(total)
                self.ultima_acc_b = f"Banca iguala y sube ${total}"
            else:
                # iguala
                pagado = self._pagar_b(tc)
                self.ultima_acc_b = f"Banca iguala ${pagado}"

        self.actuo_b = True


# ─────────────────────────── Helpers ──────────────────────────────────
def _get_sesion(session_id: str, user_id: int) -> SesionPoker:
    if session_id not in game_sessions:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    s = game_sessions[session_id]
    if not isinstance(s, SesionPoker):
        raise HTTPException(status_code=400, detail="Sesión inválida")
    if s.usuario_id != user_id:
        raise HTTPException(status_code=403, detail="Sin acceso")
    return s


def _limpiar_expiradas():
    ahora = datetime.now()
    for sid in [k for k,v in list(game_sessions.items())
                if isinstance(v, SesionPoker)
                and ahora - v.created_at > timedelta(hours=MAX_HORAS_SESION)]:
        del game_sessions[sid]


def _estado_base(s: SesionPoker) -> dict:
    return {
        "fichas_jugador":    s.fichas_j,
        "fichas_banca":      s.fichas_b,
        "bote":              s.bote,
        "apuesta_minima":    s.to_call_j(),
        "ronda_actual":      s.ronda,
        "estado":            s.ronda,
        "cartas_comunitarias": [_c(c) for c in s.comun],
        "accion_banca":      s.ultima_acc_b,
        "small_blind":       s.blind,
        "big_blind":         s.big_blind,
    }


def _resolver_showdown(s: SesionPoker, db: Session, user) -> dict:
    pool_j = s.cartas_j + s.comun
    pool_b = s.cartas_b + s.comun

    rango_j, des_j = mejor_mano(pool_j)
    rango_b, des_b = mejor_mano(pool_b)

    nombre_j = NOMBRE[rango_j]
    nombre_b = NOMBRE[rango_b]

    bote = s.bote
    ganancia = 0

    if rango_j > rango_b or (rango_j == rango_b and des_j > des_b):
        # Jugador gana
        ganancia_neta = bote - s.apuesta_ini
        user.saldo += Decimal(bote)
        resultado = f"🏆 ¡Ganaste con {nombre_j} vs {nombre_b}! +${ganancia_neta:,}"
        ganancia = ganancia_neta
    elif rango_b > rango_j or (rango_b == rango_j and des_b > des_j):
        # Banca gana
        resultado = f"❌ La banca gana con {nombre_b} vs {nombre_j}"
        ganancia = -s.apuesta_ini
    else:
        # Empate: devolver buy-in
        user.saldo += Decimal(s.apuesta_ini)
        resultado = f"🤝 Empate con {nombre_j}. Recuperas tu buy-in."
        ganancia = 0

    db.commit()
    db.refresh(user)
    del game_sessions[s.session_id]

    return {
        "resultado":           resultado,
        "ganancia":            ganancia,
        "nuevo_saldo":         float(user.saldo),
        "bote_final":          bote,
        "estado":              "terminada",
        "cartas_banca":        [_c(c) for c in s.cartas_b],
        "cartas_comunitarias": [_c(c) for c in s.comun],
        "mano_jugador":        nombre_j,
        "mano_banca":          nombre_b,
        "fichas_jugador":      s.fichas_j,
        "fichas_banca":        s.fichas_b,
        "bote":                bote,
        "apuesta_minima":      0,
        "ronda_actual":        "showdown",
    }


# ─────────────────────────── Endpoints ───────────────────────────────

@router.get("/juegos/poker/apuestas-permitidas")
def get_apuestas():
    return {"apuestas_permitidas": APUESTAS_PERMITIDAS}


@router.get("/juegos/poker/blinds")
def get_blinds():
    return {"blinds_disponibles": BLINDS_DISPONIBLES}


@router.post("/juegos/poker/iniciar")
def iniciar_poker(
    apuesta: int = Query(..., ge=1),
    blind:   int = Query(25),
    db:      Session = Depends(get_db),
    current_user: usuario.Usuario = Depends(get_current_user),
):
    _limpiar_expiradas()

    if apuesta not in APUESTAS_PERMITIDAS:
        raise HTTPException(400, f"Apuesta inválida. Opciones: {APUESTAS_PERMITIDAS}")
    if blind not in BLINDS_DISPONIBLES:
        blind = BLINDS_DISPONIBLES[0]

    user = db.query(usuario.Usuario).filter(usuario.Usuario.id == current_user.id).first()
    if not user:
        raise HTTPException(404, "Usuario no encontrado")
    if user.saldo < apuesta:
        raise HTTPException(400, f"Saldo insuficiente. Necesitas ${apuesta:,}")

    user.saldo -= Decimal(apuesta)
    db.commit()
    db.refresh(user)

    sid     = str(uuid.uuid4())
    sesion  = SesionPoker(sid, user.id, apuesta, blind)
    game_sessions[sid] = sesion

    return {
        "session_id":          sid,
        "cartas_jugador":      [_c(c) for c in sesion.cartas_j],
        "fichas_jugador":      sesion.fichas_j,
        "fichas_banca":        sesion.fichas_b,
        "bote":                sesion.bote,
        "apuesta_minima":      sesion.to_call_j(),
        "ronda_actual":        sesion.ronda,
        "estado":              sesion.ronda,
        "small_blind":         sesion.blind,
        "big_blind":           sesion.big_blind,
        "nuevo_saldo":         float(user.saldo),
        "cartas_comunitarias": [],
    }


@router.post("/juegos/poker/{session_id}/accion")
def accion_poker(
    session_id: str,
    accion:     str = Query(...),
    cantidad:   int = Query(0, ge=0),
    db:         Session = Depends(get_db),
    current_user: usuario.Usuario = Depends(get_current_user),
):
    _limpiar_expiradas()
    s = _get_sesion(session_id, current_user.id)

    if s.terminada:
        raise HTTPException(400, "La partida ya terminó")
    if s.actuo_j:
        raise HTTPException(400, "Ya realizaste tu acción en esta ronda")

    user = db.query(usuario.Usuario).filter(usuario.Usuario.id == current_user.id).first()
    if not user:
        raise HTTPException(404, "Usuario no encontrado")

    accion = accion.lower().strip()

    # ── Acción del jugador ──────────────────────────────────────────
    if accion == "retirarse":
        # Jugador se retira: pierde lo apostado en el bote
        ganancia  = -s.apuesta_ini
        bote_final = s.bote
        del game_sessions[session_id]
        return {
            "resultado":           "Te retiraste. La banca gana el bote.",
            "ganancia":            ganancia,
            "nuevo_saldo":         float(user.saldo),
            "bote_final":          bote_final,
            "estado":              "terminada",
            "cartas_banca":        [_c(c) for c in s.cartas_b],
            "cartas_comunitarias": [_c(c) for c in s.comun],
            "mano_jugador":        "Se retiró",
            "mano_banca":          "",
            "fichas_jugador":      s.fichas_j,
            "fichas_banca":        s.fichas_b,
            "bote":                bote_final,
            "apuesta_minima":      0,
            "ronda_actual":        s.ronda,
        }

    elif accion == "pasar":
        tc = s.to_call_j()
        if tc > 0:
            raise HTTPException(400, f"No puedes pasar: hay una apuesta de ${tc:,} para igualar")
        s.ultima_acc_b = ""

    elif accion == "igualar":
        tc = s.to_call_j()
        if tc <= 0:
            # ya igualado → pasar
            pass
        else:
            if s.fichas_j < tc:
                raise HTTPException(400, f"Fichas insuficientes. Necesitas ${tc:,}")
            s._pagar_j(tc)

    elif accion == "subir":
        tc      = s.to_call_j()
        min_sub = tc + s.big_blind
        if cantidad < min_sub:
            raise HTTPException(400, f"Subida mínima: ${min_sub:,}")
        if cantidad > s.fichas_j:
            raise HTTPException(400, f"Fichas insuficientes. Tienes ${s.fichas_j:,}")
        s._pagar_j(cantidad)

    else:
        raise HTTPException(400, f"Acción desconocida: {accion}")

    s.actuo_j = True

    # ── Acción de la banca ─────────────────────────────────────────
    s._banca_actua()

    # ── ¿Avanzar ronda? ───────────────────────────────────────────
    # Ambos actuaron; igualamos apuestas si fuera necesario después de subidas
    # Si la banca subió y el jugador no igualó esa subida, el jugador puede volver a actuar
    # (Simplificado: 1 acción por calle, siempre avanzamos si los dos actuaron)
    if s.actuo_j and s.actuo_b:
        if s.ronda == "river":
            # Ir a showdown
            s._reset_calle()
            s.ronda = "showdown"
            return _resolver_showdown(s, db, user)

        s._avanzar_ronda()

    if s.ronda == "showdown":
        return _resolver_showdown(s, db, user)

    resp = _estado_base(s)
    return resp


@router.get("/juegos/poker/{session_id}/estado")
def estado_poker(
    session_id: str,
    current_user: usuario.Usuario = Depends(get_current_user),
):
    _limpiar_expiradas()
    s = _get_sesion(session_id, current_user.id)
    resp = _estado_base(s)
    resp["session_id"]   = session_id
    resp["cartas_jugador"] = [_c(c) for c in s.cartas_j]
    return resp


@router.post("/juegos/poker/{session_id}/rendirse")
def rendirse_poker(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: usuario.Usuario = Depends(get_current_user),
):
    _limpiar_expiradas()
    s    = _get_sesion(session_id, current_user.id)
    user = db.query(usuario.Usuario).filter(usuario.Usuario.id == current_user.id).first()
    if not user:
        raise HTTPException(404, "Usuario no encontrado")

    # Devolvemos la mitad del buy-in como consolación
    devolucion = s.apuesta_ini // 2
    user.saldo += Decimal(devolucion)
    db.commit()
    db.refresh(user)
    del game_sessions[session_id]

    return {
        "resultado":   f"Te rendiste. Recuperas ${devolucion:,} (mitad de tu buy-in).",
        "devolucion":  devolucion,
        "ganancia":    devolucion - s.apuesta_ini,
        "nuevo_saldo": float(user.saldo),
        "estado":      "terminada",
    }
