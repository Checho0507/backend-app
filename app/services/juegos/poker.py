from __future__ import annotations

from datetime import datetime, timedelta
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
    VER = "ver"
    APOSTAR = "apostar"

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
    TERMINADA = "terminada"
    SHOWDOWN = "showdown"

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
    __slots__ = ("usuario_id", "cartas", "fichas", "apuesta_actual", "esta_en_juego", 
                 "es_ganador", "ultima_accion", "es_dealer", "es_small_blind", "es_big_blind")
    
    def __init__(self, usuario_id: int, fichas_iniciales: int):
        self.usuario_id = usuario_id
        self.cartas: List[CartaPoker] = []
        self.fichas = fichas_iniciales
        self.apuesta_actual = 0
        self.esta_en_juego = True
        self.es_ganador = False
        self.ultima_accion: Optional[str] = None
        self.es_dealer = False
        self.es_small_blind = False
        self.es_big_blind = False
    
    def apostar(self, cantidad: int) -> bool:
        if cantidad > self.fichas:
            return False
        self.fichas -= cantidad
        self.apuesta_actual += cantidad
        return True
    
    def reiniciar_apuesta_ronda(self):
        self.apuesta_actual = 0
    
    def recibir_cartas(self, cartas: List[CartaPoker]):
        self.cartas = cartas
    
    def retirarse(self):
        self.esta_en_juego = False
        self.ultima_accion = "retirarse"
    
    def puede_jugar(self) -> bool:
        return self.esta_en_juego

class MesaPoker:
    __slots__ = ("cartas_comunitarias", "bote", "apuesta_minima", "ronda_actual", 
                 "jugadores", "dealer_index", "turno_actual", "small_blind", "big_blind")
    
    def __init__(self, small_blind: int = 10):
        self.cartas_comunitarias: List[CartaPoker] = []
        self.bote = 0
        self.apuesta_minima = 0
        self.ronda_actual = EstadoPartida.PRE_FLOP
        self.jugadores: List[JugadorPoker] = []
        self.dealer_index = 0
        self.turno_actual = 0
        self.small_blind = small_blind
        self.big_blind = small_blind * 2
    
    def agregar_jugador(self, jugador: JugadorPoker):
        self.jugadores.append(jugador)
    
    def siguiente_turno(self):
        # Encontrar siguiente jugador que esté en juego
        start_index = self.turno_actual
        while True:
            self.turno_actual = (self.turno_actual + 1) % len(self.jugadores)
            if self.turno_actual == start_index:
                break
            if self.jugadores[self.turno_actual].puede_jugar():
                return
        # Si todos están fuera, terminar ronda
    
    def agregar_al_bote(self, cantidad: int):
        self.bote += cantidad
    
    def repartir_comunitarias(self, cantidad: int, baraja: List[CartaPoker]) -> List[CartaPoker]:
        cartas = baraja[:cantidad]
        del baraja[:cantidad]
        self.cartas_comunitarias.extend(cartas)
        return cartas
    
    def avanzar_ronda(self):
        rondas = list(EstadoPartida)
        current_index = rondas.index(self.ronda_actual)
        if current_index < len(rondas) - 2:  # No avanzar a TERMINADA automáticamente
            self.ronda_actual = rondas[current_index + 1]
            # Reiniciar apuestas de la ronda para todos los jugadores
            for jugador in self.jugadores:
                jugador.reiniciar_apuesta_ronda()
            self.apuesta_minima = 0

class SesionPoker:
    __slots__ = ("session_id", "mesa", "baraja", "usuario_id", "apuesta_inicial", 
                 "created_at", "estado", "banca_id", "historico_acciones")
    
    def __init__(self, session_id: str, usuario_id: int, apuesta: int, banca_id: int = 0):
        self.session_id = session_id
        self.usuario_id = usuario_id
        self.apuesta_inicial = apuesta
        self.created_at = datetime.now()
        self.estado = "activa"
        self.banca_id = banca_id
        self.historico_acciones: List[Dict] = []
        
        # Inicializar mesa
        self.mesa = MesaPoker(small_blind=min(APUESTAS_PERMITIDAS) // 20)
        self.baraja = self.crear_baraja()
        random.shuffle(self.baraja)
        
        # Crear jugadores
        jugador_humano = JugadorPoker(usuario_id, apuesta * 10)  # 10x buy-in
        jugador_banca = JugadorPoker(banca_id, apuesta * 10)
        
        # Asignar posiciones (simplificado)
        jugador_humano.es_dealer = True
        jugador_banca.es_big_blind = True
        
        self.mesa.agregar_jugador(jugador_humano)
        self.mesa.agregar_jugador(jugador_banca)
    
    def crear_baraja(self) -> List[CartaPoker]:
        baraja = []
        for palo in Palo:
            for valor in ValorCarta:
                baraja.append(CartaPoker(valor, palo))
        return baraja
    
    def repartir_cartas_privadas(self):
        for jugador in self.mesa.jugadores:
            cartas = [self.baraja.pop() for _ in range(2)]
            jugador.recibir_cartas(cartas)
    
    def procesar_blinds(self):
        # Small blind y big blind
        for jugador in self.mesa.jugadores:
            if jugador.es_small_blind:
                apuesta = min(self.mesa.small_blind, jugador.fichas)
                jugador.apostar(apuesta)
                self.mesa.agregar_al_bote(apuesta)
            elif jugador.es_big_blind:
                apuesta = min(self.mesa.big_blind, jugador.fichas)
                jugador.apostar(apuesta)
                self.mesa.apuesta_minima = apuesta
                self.mesa.agregar_al_bote(apuesta)
    
    def evaluar_mano(self, cartas: List[CartaPoker]) -> Tuple[ManoPoker, List[int]]:
        """Evalúa una mano de poker y retorna (tipo_de_mano, valores_relevantes)"""
        todas_las_cartas = cartas
        valores = sorted([c.valor_numerico() for c in todas_las_cartas], reverse=True)
        palos = [c.palo for c in todas_las_cartas]
        
        # Contar palos
        conteo_palos = {}
        for palo in palos:
            conteo_palos[palo] = conteo_palos.get(palo, 0) + 1
        
        # Contar valores
        conteo_valores = {}
        for valor in valores:
            conteo_valores[valor] = conteo_valores.get(valor, 0) + 1
        
        # Ordenar por frecuencia y valor
        valores_ordenados = sorted(conteo_valores.items(), key=lambda x: (x[1], x[0]), reverse=True)
        
        # Verificar escalera real
        valores_especiales = {10, 11, 12, 13, 14}
        escalera_real = False
        for palo in Palo:
            valores_en_palo = {c.valor_numerico() for c in todas_las_cartas if c.palo == palo}
            if valores_especiales.issubset(valores_en_palo):
                escalera_real = True
                break
        
        # Verificar escalera color
        escalera_color = False
        for palo, count in conteo_palos.items():
            if count >= 5:
                valores_en_palo = sorted([c.valor_numerico() for c in todas_las_cartas if c.palo == palo], reverse=True)
                # Buscar escalera en estos valores
                for i in range(len(valores_en_palo) - 4):
                    if valores_en_palo[i] - valores_en_palo[i+4] == 4:
                        escalera_color = True
                        break
        
        # Verificar poker
        poker = any(count == 4 for count in conteo_valores.values())
        
        # Verificar full house
        full_house = False
        if len(valores_ordenados) >= 2:
            full_house = valores_ordenados[0][1] >= 3 and valores_ordenados[1][1] >= 2
        
        # Verificar color
        color = any(count >= 5 for count in conteo_palos.values())
        
        # Verificar escalera
        escalera = False
        valores_unicos = sorted(set(valores), reverse=True)
        for i in range(len(valores_unicos) - 4):
            if valores_unicos[i] - valores_unicos[i+4] == 4:
                escalera = True
                break
        # Escalera con As como 1
        if 14 in valores_unicos:
            valores_con_as_bajo = valores_unicos.copy()
            valores_con_as_bajo.remove(14)
            valores_con_as_bajo.append(1)
            valores_con_as_bajo.sort(reverse=True)
            for i in range(len(valores_con_as_bajo) - 4):
                if valores_con_as_bajo[i] - valores_con_as_bajo[i+4] == 4:
                    escalera = True
                    break
        
        # Verificar trio
        trio = any(count == 3 for count in conteo_valores.values())
        
        # Verificar pares
        pares = [valor for valor, count in conteo_valores.items() if count == 2]
        doble_par = len(pares) >= 2
        par = len(pares) == 1
        
        # Determinar mano
        if escalera_real:
            return ManoPoker.ESCALERA_REAL, [14, 13, 12, 11, 10]
        elif escalera_color:
            return ManoPoker.ESCALERA_COLOR, valores[:5]
        elif poker:
            valor_poker = next(valor for valor, count in conteo_valores.items() if count == 4)
            kicker = max(v for v in valores if v != valor_poker)
            return ManoPoker.POKER, [valor_poker, kicker]
        elif full_house:
            trio_val = valores_ordenados[0][0]
            par_val = valores_ordenados[1][0]
            return ManoPoker.FULL_HOUSE, [trio_val, par_val]
        elif color:
            valores_color = sorted([c.valor_numerico() for c in todas_las_cartas 
                                  if c.palo == max(conteo_palos, key=conteo_palos.get)], reverse=True)
            return ManoPoker.COLOR, valores_color[:5]
        elif escalera:
            return ManoPoker.ESCALERA, valores[:5]
        elif trio:
            trio_val = next(valor for valor, count in conteo_valores.items() if count == 3)
            kickers = sorted([v for v in valores if v != trio_val], reverse=True)[:2]
            return ManoPoker.TRIO, [trio_val] + kickers
        elif doble_par:
            pares_ordenados = sorted(pares, reverse=True)
            kicker = max(v for v in valores if v not in pares_ordenados)
            return ManoPoker.DOBLE_PAR, pares_ordenados + [kicker]
        elif par:
            par_val = pares[0]
            kickers = sorted([v for v in valores if v != par_val], reverse=True)[:3]
            return ManoPoker.PAR, [par_val] + kickers
        else:
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
            # Si no es una sesión de poker, también limpiar
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
    return {
        "valor": carta.nombre(),
        "palo": carta.palo.value,
        "valor_numerico": carta.valor_numerico()
    }

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
    current_user: usuario.Usuario = Depends(get_current_user)
):
    limpiar_sesiones_expiradas()
    
    if apuesta not in APUESTAS_PERMITIDAS:
        raise HTTPException(
            status_code=400,
            detail=f"Apuesta no válida. Debe ser una de {APUESTAS_PERMITIDAS}"
        )
    
    if blind not in BLINDS:
        raise HTTPException(
            status_code=400,
            detail=f"Blind no válido. Debe ser uno de {BLINDS}"
        )
    
    user = db.query(usuario.Usuario).filter(usuario.Usuario.id == current_user.id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    if user.saldo < apuesta:
        raise HTTPException(status_code=400, detail=f"Saldo insuficiente. Necesitas ${apuesta} para jugar.")
    
    # Descontar buy-in
    user.saldo -= apuesta
    db.commit()
    db.refresh(user)
    
    # Crear nueva sesión
    session_id = str(uuid.uuid4())
    sesion = SesionPoker(session_id, user.id, apuesta)
    sesion.mesa.small_blind = blind
    sesion.mesa.big_blind = blind * 2
    
    # Repartir cartas
    sesion.repartir_cartas_privadas()
    sesion.procesar_blinds()
    
    # Guardar sesión
    game_sessions[session_id] = sesion
    
    # Preparar respuesta
    jugador = sesion.mesa.jugadores[0]
    banca = sesion.mesa.jugadores[1]
    
    return {
        "session_id": session_id,
        "cartas_jugador": [carta_a_dict(c) for c in jugador.cartas],
        "fichas_jugador": jugador.fichas,
        "fichas_banca": banca.fichas,
        "bote": sesion.mesa.bote,
        "apuesta_minima": sesion.mesa.apuesta_minima,
        "ronda_actual": sesion.mesa.ronda_actual.value,
        "turno_actual": "jugador",  # El jugador humano empieza
        "small_blind": sesion.mesa.small_blind,
        "big_blind": sesion.mesa.big_blind,
        "nuevo_saldo": user.saldo,
        "cartas_comunitarias": [],
        "estado": "pre_flop"
    }

@router.post("/juegos/poker/{session_id}/accion")
def realizar_accion(
    session_id: str,
    accion: str = Query(..., description="Acción a realizar"),
    cantidad: int = Query(0, description="Cantidad para subir/apostar"),
    db: Session = Depends(get_db),
    current_user: usuario.Usuario = Depends(get_current_user)
):
    limpiar_sesiones_expiradas()
    sesion = obtener_sesion_poker(session_id, current_user.id)
    
    user = db.query(usuario.Usuario).filter(usuario.Usuario.id == current_user.id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    jugador = sesion.mesa.jugadores[0]
    banca = sesion.mesa.jugadores[1]
    
    if not jugador.puede_jugar():
        raise HTTPException(status_code=400, detail="El jugador ya se retiró")
    
    # Validar acción
    accion_valida = False
    monto_valido = True
    
    if accion == "ver" and jugador.apuesta_actual >= sesion.mesa.apuesta_minima:
        accion_valida = True
        jugador.ultima_accion = "ver"
    
    elif accion == "igualar":
        cantidad_necesaria = sesion.mesa.apuesta_minima - jugador.apuesta_actual
        if cantidad_necesaria <= jugador.fichas:
            accion_valida = True
            jugador.apostar(cantidad_necesaria)
            sesion.mesa.agregar_al_bote(cantidad_necesaria)
            jugador.ultima_accion = "igualar"
        else:
            monto_valido = False
    
    elif accion == "subir":
        if cantidad >= sesion.mesa.apuesta_minima * 2 and cantidad <= jugador.fichas:
            accion_valida = True
            jugador.apostar(cantidad)
            sesion.mesa.apuesta_minima = cantidad
            sesion.mesa.agregar_al_bote(cantidad)
            jugador.ultima_accion = "subir"
        else:
            monto_valido = False
    
    elif accion == "pasar":
        if sesion.mesa.apuesta_minima == 0:
            accion_valida = True
            jugador.ultima_accion = "pasar"
        else:
            raise HTTPException(status_code=400, detail="No puedes pasar cuando hay apuesta pendiente")
    
    elif accion == "retirarse":
        accion_valida = True
        jugador.retirarse()
        jugador.ultima_accion = "retirarse"
    
    if not accion_valida:
        raise HTTPException(
            status_code=400,
            detail=f"Acción '{accion}' no válida en este momento"
        )
    
    if not monto_valido:
        raise HTTPException(status_code=400, detail="Monto no válido o insuficiente")
    
    # Registrar acción
    sesion.historico_acciones.append({
        "jugador": "usuario",
        "accion": accion,
        "cantidad": cantidad if accion in ["subir", "apostar"] else 0,
        "timestamp": datetime.now().isoformat()
    })
    
    # Si jugador se retira, terminar juego
    if accion == "retirarse":
        # La banca gana el bote
        banca.fichas += sesion.mesa.bote
        sesion.mesa.bote = 0
        sesion.estado = "terminada"
        
        # Calcular ganancia/pérdida
        ganancia = -sesion.apuesta_inicial  # Pierde su buy-in
        
        del game_sessions[session_id]
        
        return {
            "resultado": "Te retiraste. La banca gana el bote.",
            "ganancia": ganancia,
            "nuevo_saldo": user.saldo,
            "bote_final": 0,
            "estado": "terminada"
        }
    
    # Turno de la banca (IA simplificada)
    acciones_banca = ["ver", "igualar", "subir", "retirarse"]
    
    # Evaluar mano de la banca
    mano_banca, _ = sesion.evaluar_mano(banca.cartas + sesion.mesa.cartas_comunitarias)
    fuerza_mano = mano_banca.value
    
    # Decisión basada en fuerza de mano
    if fuerza_mano >= ManoPoker.PAR.value:
        # Mano buena: subir o igualar
        if random.random() < 0.7:  # 70% de probabilidad de subir con buena mano
            subida_banca = min(sesion.mesa.apuesta_minima * 2, banca.fichas)
            banca.apostar(subida_banca)
            sesion.mesa.apuesta_minima = subida_banca
            sesion.mesa.agregar_al_bote(subida_banca)
            accion_banca = "subir"
        else:
            if sesion.mesa.apuesta_minima > 0:
                cantidad_necesaria = sesion.mesa.apuesta_minima - banca.apuesta_actual
                if cantidad_necesaria <= banca.fichas:
                    banca.apostar(cantidad_necesaria)
                    sesion.mesa.agregar_al_bote(cantidad_necesaria)
                    accion_banca = "igualar"
                else:
                    banca.retirarse()
                    accion_banca = "retirarse"
            else:
                accion_banca = "ver"
    else:
        # Mano mala: ver o retirarse
        if random.random() < 0.4:  # 40% de bluff
            if sesion.mesa.apuesta_minima > 0:
                cantidad_necesaria = sesion.mesa.apuesta_minima - banca.apuesta_actual
                if cantidad_necesaria <= banca.fichas:
                    banca.apostar(cantidad_necesaria)
                    sesion.mesa.agregar_al_bote(cantidad_necesaria)
                    accion_banca = "igualar"
                else:
                    banca.retirarse()
                    accion_banca = "retirarse"
            else:
                accion_banca = "ver"
        else:
            banca.retirarse()
            accion_banca = "retirarse"
    
    # Registrar acción de la banca
    sesion.historico_acciones.append({
        "jugador": "banca",
        "accion": accion_banca,
        "cantidad": subida_banca if accion_banca == "subir" else 0,
        "timestamp": datetime.now().isoformat()
    })
    
    # Si banca se retira, jugador gana
    if accion_banca == "retirarse":
        jugador.fichas += sesion.mesa.bote
        sesion.mesa.bote = 0
        sesion.estado = "terminada"
        
        ganancia = sesion.mesa.bote - sesion.apuesta_inicial
        user.saldo += ganancia + sesion.apuesta_inicial  # Devuelve buy-in + ganancia
        db.commit()
        
        del game_sessions[session_id]
        
        return {
            "resultado": "La banca se retiró. ¡Ganaste el bote!",
            "ganancia": ganancia,
            "nuevo_saldo": user.saldo,
            "bote_final": 0,
            "estado": "terminada",
            "cartas_banca": [carta_a_dict(c) for c in banca.cartas]
        }
    
    # Verificar si ronda terminó (ambos han apostado igual)
    if jugador.apuesta_actual == banca.apuesta_actual and jugador.apuesta_actual >= sesion.mesa.apuesta_minima:
        # Avanzar ronda o terminar
        if sesion.mesa.ronda_actual == EstadoPartida.PRE_FLOP:
            sesion.mesa.avanzar_ronda()
            # Repartir flop
            cartas_flop = sesion.mesa.repartir_comunitarias(3, sesion.baraja)
        elif sesion.mesa.ronda_actual == EstadoPartida.FLOP:
            sesion.mesa.avanzar_ronda()
            # Repartir turn
            cartas_turn = sesion.mesa.repartir_comunitarias(1, sesion.baraja)
        elif sesion.mesa.ronda_actual == EstadoPartida.TURN:
            sesion.mesa.avanzar_ronda()
            # Repartir river
            cartas_river = sesion.mesa.repartir_comunitarias(1, sesion.baraja)
        elif sesion.mesa.ronda_actual == EstadoPartida.RIVER:
            # SHOWDOWN - evaluar manos
            sesion.mesa.ronda_actual = EstadoPartida.SHOWDOWN
            sesion.estado = "showdown"
    
    # Si es showdown, determinar ganador
    if sesion.estado == "showdown":
        # Evaluar manos
        mano_jugador, valores_jugador = sesion.evaluar_mano(jugador.cartas + sesion.mesa.cartas_comunitarias)
        mano_banca_eval, valores_banca = sesion.evaluar_mano(banca.cartas + sesion.mesa.cartas_comunitarias)
        
        resultado = ""
        ganador = None
        
        # Comparar manos
        if mano_jugador.value > mano_banca_eval.value:
            ganador = jugador
            resultado = f"¡Ganaste con {mano_jugador.name.replace('_', ' ').title()}!"
        elif mano_banca_eval.value > mano_jugador.value:
            ganador = banca
            resultado = f"La banca gana con {mano_banca_eval.name.replace('_', ' ').title()}."
        else:
            # Empate en tipo de mano, comparar valores
            for vj, vb in zip(valores_jugador, valores_banca):
                if vj > vb:
                    ganador = jugador
                    resultado = f"¡Ganaste con {mano_jugador.name.replace('_', ' ').title()} (carta más alta)!"
                    break
                elif vb > vj:
                    ganador = banca
                    resultado = f"La banca gana con {mano_banca_eval.name.replace('_', ' ').title()} (carta más alta)."
                    break
            else:
                # Empate total
                resultado = "¡Empate! El bote se divide."
                # Dividir bote
                mitad_bote = sesion.mesa.bote // 2
                jugador.fichas += mitad_bote
                banca.fichas += sesion.mesa.bote - mitad_bote
        
        if ganador == jugador:
            jugador.fichas += sesion.mesa.bote
            ganancia = sesion.mesa.bote - sesion.apuesta_inicial
            user.saldo += ganancia + sesion.apuesta_inicial  # Devuelve buy-in + ganancia
        elif ganador == banca:
            banca.fichas += sesion.mesa.bote
            ganancia = -sesion.apuesta_inicial  # Pierde buy-in
        else:  # Empate
            mitad_bote = sesion.mesa.bote // 2
            jugador.fichas += mitad_bote
            ganancia = mitad_bote - sesion.apuesta_inicial
            user.saldo += ganancia + sesion.apuesta_inicial
        
        sesion.mesa.bote = 0
        sesion.estado = "terminada"
        
        db.commit()
        db.refresh(user)
        
        del game_sessions[session_id]
        
        return {
            "resultado": resultado,
            "ganancia": ganancia,
            "nuevo_saldo": user.saldo,
            "bote_final": 0,
            "estado": "terminada",
            "cartas_banca": [carta_a_dict(c) for c in banca.cartas],
            "cartas_comunitarias": [carta_a_dict(c) for c in sesion.mesa.cartas_comunitarias],
            "mano_jugador": mano_jugador.name.replace('_', ' ').title(),
            "mano_banca": mano_banca_eval.name.replace('_', ' ').title()
        }
    
    # Continuar juego
    return {
        "fichas_jugador": jugador.fichas,
        "fichas_banca": banca.fichas,
        "bote": sesion.mesa.bote,
        "apuesta_minima": sesion.mesa.apuesta_minima,
        "ronda_actual": sesion.mesa.ronda_actual.value,
        "cartas_comunitarias": [carta_a_dict(c) for c in sesion.mesa.cartas_comunitarias],
        "accion_banca": accion_banca,
        "estado": "continuando"
    }

@router.post("/juegos/poker/{session_id}/rendirse")
def rendirse(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: usuario.Usuario = Depends(get_current_user)
):
    """Rendirse y recuperar parte del buy-in"""
    limpiar_sesiones_expiradas()
    sesion = obtener_sesion_poker(session_id, current_user.id)
    
    user = db.query(usuario.Usuario).filter(usuario.Usuario.id == current_user.id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    # Devolver 50% del buy-in
    devolucion = sesion.apuesta_inicial // 2
    user.saldo += devolucion
    db.commit()
    
    del game_sessions[session_id]
    
    return {
        "resultado": "Te rendiste. Recuperaste el 50% de tu buy-in.",
        "devolucion": devolucion,
        "nuevo_saldo": user.saldo,
        "estado": "terminada"
    }

@router.get("/juegos/poker/{session_id}/estado")
def obtener_estado(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: usuario.Usuario = Depends(get_current_user)
):
    """Obtener estado actual del juego"""
    limpiar_sesiones_expiradas()
    sesion = obtener_sesion_poker(session_id, current_user.id)
    
    jugador = sesion.mesa.jugadores[0]
    banca = sesion.mesa.jugadores[1]
    
    return {
        "session_id": session_id,
        "cartas_jugador": [carta_a_dict(c) for c in jugador.cartas],
        "fichas_jugador": jugador.fichas,
        "fichas_banca": banca.fichas,
        "bote": sesion.mesa.bote,
        "apuesta_minima": sesion.mesa.apuesta_minima,
        "ronda_actual": sesion.mesa.ronda_actual.value,
        "cartas_comunitarias": [carta_a_dict(c) for c in sesion.mesa.cartas_comunitarias],
        "estado": sesion.estado,
        "ultima_accion_jugador": jugador.ultima_accion,
        "ultima_accion_banca": banca.ultima_accion,
        "turno_actual": "jugador" if sesion.mesa.turno_actual == 0 else "banca"
    }