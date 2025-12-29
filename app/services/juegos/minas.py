import os
import uuid
import json
from random import sample
from typing import List, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime

# Ajusta estas importaciones según tu estructura de proyecto
from ...database import get_db
from ...api.auth import get_current_user
from ...models.usuario import Usuario

router = APIRouter()

# Configuración del juego mejorada
MINAS_CONFIG = {
    "facil": {"tamano": 5, "minas": 5, "multiplicador_base": 1.05},
    "medio": {"tamano": 6, "minas": 10, "multiplicador_base": 1.10},
    "dificil": {"tamano": 7, "minas": 20, "multiplicador_base": 1.15}
}

# Sesiones activas de juego
sesiones_activas = {}

class JuegoMinas:
    def __init__(self, usuario_id: int, username: str, apuesta: int, dificultad: str):
        self.id = str(uuid.uuid4())
        self.usuario_id = usuario_id
        self.username = username
        self.apuesta = apuesta
        self.dificultad = dificultad
        
        config = MINAS_CONFIG[dificultad]
        self.tamano = config["tamano"]
        self.minas_totales = config["minas"]
        self.multiplicador_base = config["multiplicador_base"]
        
        # Generar tablero
        self.tablero = self._generar_tablero()
        self.casillas_abiertas = []
        self.casillas_marcadas = []
        self.game_over = False
        self.ganado = False
        self.ganancia_actual = apuesta  # Inicia con la apuesta base
        self.multiplicador_actual = 1.0
        self.fecha_inicio = datetime.now()
        
    def _generar_tablero(self) -> List[List[Dict]]:
        """Genera un tablero con minas aleatorias"""
        tamano = self.tamano
        total_casillas = tamano * tamano
        
        # Crear lista de posiciones de minas
        posiciones_minas = sample(range(total_casillas), self.minas_totales)
        
        tablero = []
        for i in range(tamano):
            fila = []
            for j in range(tamano):
                posicion = i * tamano + j
                es_mine = posicion in posiciones_minas
                fila.append({
                    "x": i,
                    "y": j,
                    "es_mine": es_mine,
                    "abierta": False,
                    "marcada": False,
                    "minas_cercanas": 0
                })
            tablero.append(fila)
        
        # Calcular minas cercanas para cada casilla
        for i in range(tamano):
            for j in range(tamano):
                if not tablero[i][j]["es_mine"]:
                    minas_cercanas = self._contar_minas_cercanas(tablero, i, j)
                    tablero[i][j]["minas_cercanas"] = minas_cercanas
        
        return tablero
    
    def _contar_minas_cercanas(self, tablero: List[List[Dict]], x: int, y: int) -> int:
        """Cuenta las minas alrededor de una casilla"""
        tamano = self.tamano
        direcciones = [(-1, -1), (-1, 0), (-1, 1),
                      (0, -1),          (0, 1),
                      (1, -1),  (1, 0), (1, 1)]
        
        contador = 0
        for dx, dy in direcciones:
            nx, ny = x + dx, y + dy
            if 0 <= nx < tamano and 0 <= ny < tamano:
                if tablero[nx][ny]["es_mine"]:
                    contador += 1
        return contador
    
    def abrir_casilla(self, x: int, y: int) -> Dict:
        """Abre una casilla del tablero"""
        if self.game_over or self.ganado:
            raise ValueError("El juego ya ha terminado")
        
        # Validar coordenadas
        if not (0 <= x < self.tamano and 0 <= y < self.tamano):
            raise ValueError(f"Coordenadas inválidas: ({x}, {y})")
        
        casilla = self.tablero[x][y]
        
        if casilla["abierta"]:
            raise ValueError("Casilla ya abierta")
        
        if casilla["marcada"]:
            raise ValueError("Casilla marcada con bandera")
        
        # Si es mina, fin del juego
        if casilla["es_mine"]:
            casilla["abierta"] = True
            self.game_over = True
            self.ganancia_actual = 0
            return {
                "es_mine": True,
                "game_over": True,
                "ganado": False,
                "ganancia": 0,
                "mensaje": "¡Boom! Encontraste una mina"
            }
        
        # Abrir casilla segura
        casillas_abiertas_antes = len(self.casillas_abiertas)
        self._abrir_casilla_recursiva(x, y)
        nuevas_abiertas = len(self.casillas_abiertas) - casillas_abiertas_antes
        
        # Calcular nueva ganancia
        self.multiplicador_actual = 1.0 + (len(self.casillas_abiertas) * (self.multiplicador_base - 1))
        self.ganancia_actual = int(self.apuesta * self.multiplicador_actual)
        
        # Verificar si ganó
        casillas_seguras = (self.tamano * self.tamano) - self.minas_totales
        if len(self.casillas_abiertas) == casillas_seguras:
            self.ganado = True
            self.game_over = True
            return {
                "es_mine": False,
                "game_over": True,
                "ganado": True,
                "ganancia": self.ganancia_actual,
                "mensaje": f"¡Ganaste ${self.ganancia_actual}!",
                "minas_cercanas": casilla["minas_cercanas"]
            }
        
        return {
            "es_mine": False,
            "game_over": False,
            "ganado": False,
            "ganancia": self.ganancia_actual,
            "minas_cercanas": casilla["minas_cercanas"],
            "nuevas_abiertas": nuevas_abiertas,
            "mensaje": f"Casilla segura. Multiplicador: {self.multiplicador_actual:.2f}x"
        }
    
    def _abrir_casilla_recursiva(self, x: int, y: int):
        """Abre casillas recursivamente si no tienen minas cercanas"""
        if not (0 <= x < self.tamano and 0 <= y < self.tamano):
            return
        
        casilla = self.tablero[x][y]
        if casilla["abierta"] or casilla["marcada"] or casilla["es_mine"]:
            return
        
        casilla["abierta"] = True
        if (x, y) not in self.casillas_abiertas:
            self.casillas_abiertas.append((x, y))
        
        # Si no tiene minas cercanas, abrir vecinos
        if casilla["minas_cercanas"] == 0:
            direcciones = [(-1, -1), (-1, 0), (-1, 1),
                          (0, -1),          (0, 1),
                          (1, -1),  (1, 0), (1, 1)]
            for dx, dy in direcciones:
                self._abrir_casilla_recursiva(x + dx, y + dy)
    
    def marcar_casilla(self, x: int, y: int) -> bool:
        """Marca/desmarca una casilla con bandera"""
        if not (0 <= x < self.tamano and 0 <= y < self.tamano):
            raise ValueError("Coordenadas inválidas")
        
        casilla = self.tablero[x][y]
        if casilla["abierta"]:
            return False
        
        casilla["marcada"] = not casilla["marcada"]
        if casilla["marcada"]:
            if (x, y) not in self.casillas_marcadas:
                self.casillas_marcadas.append((x, y))
        else:
            if (x, y) in self.casillas_marcadas:
                self.casillas_marcadas.remove((x, y))
        
        return casilla["marcada"]
    
    def retirarse(self) -> int:
        """El jugador se retira con la ganancia actual"""
        if self.game_over:
            raise ValueError("El juego ya ha terminado")
        
        self.game_over = True
        return self.ganancia_actual
    
    def obtener_estado(self) -> Dict:
        """Obtiene el estado completo del juego para el frontend"""
        return {
            "session_id": self.id,
            "usuario_id": self.usuario_id,
            "username": self.username,
            "apuesta": self.apuesta,
            "dificultad": self.dificultad,
            "tamano": self.tamano,
            "minas_totales": self.minas_totales,
            "minas_restantes": self.minas_totales - len(self.casillas_marcadas),
            "casillas_abiertas": len(self.casillas_abiertas),
            "casillas_marcadas": self.casillas_marcadas,
            "game_over": self.game_over,
            "ganado": self.ganado,
            "multiplicador_actual": self.multiplicador_actual,
            "ganancia_actual": self.ganancia_actual,
            "fecha_inicio": self.fecha_inicio.isoformat()
        }

@router.post("/iniciar")
def iniciar_minas(
    apuesta: int,
    dificultad: str = "facil",
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)  # Cambiado: Usuario en lugar de dict
):
    """Inicia un nuevo juego de minas"""
    print(f"🔍 Solicitud recibida - apuesta: {apuesta}, dificultad: {dificultad}")
    print(f"👤 Usuario: {current_user.username} (ID: {current_user.id})")
    
    # Verificar si el usuario ya tiene un juego activo
    for juego_id, juego in list(sesiones_activas.items()):
        if juego.usuario_id == current_user.id:  # Cambiado: current_user.id en lugar de current_user["id"]
            # Limpiar juego anterior
            del sesiones_activas[juego_id]
    
    if dificultad not in MINAS_CONFIG:
        raise HTTPException(status_code=400, detail="Dificultad no válida. Opciones: facil, medio, dificil")
    
    if apuesta < 100:
        raise HTTPException(status_code=400, detail="La apuesta mínima es $100")
    
    # Obtener usuario desde la base de datos (ya está cargado en current_user)
    user = db.query(Usuario).filter(Usuario.id == current_user.id).first()  # Cambiado: current_user.id
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    if user.saldo < apuesta:
        raise HTTPException(
            status_code=400, 
            detail=f"Saldo insuficiente. Tienes ${user.saldo}, necesitas ${apuesta} para jugar."
        )
    
    # Descontar apuesta
    user.saldo -= apuesta
    db.commit()
    db.refresh(user)
    
    # Crear nuevo juego
    juego = JuegoMinas(
        usuario_id=user.id,
        username=user.username,
        apuesta=apuesta,
        dificultad=dificultad
    )
    
    # Guardar en sesiones activas
    sesiones_activas[juego.id] = juego
    
    # Obtener config para respuesta
    config = MINAS_CONFIG[dificultad]
    
    return {
        "success": True,
        "session_id": juego.id,
        "tamano": config["tamano"],
        "minas_totales": config["minas"],
        "apuesta": apuesta,
        "dificultad": dificultad,
        "multiplicador_base": config["multiplicador_base"],
        "nuevo_saldo": user.saldo,
        "mensaje": f"¡Juego iniciado! Encuentra {config['minas']} minas en un tablero {config['tamano']}x{config['tamano']}"
    }

@router.post("/{session_id}/abrir")
def abrir_casilla(
    session_id: str,
    x: int,
    y: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)  # Cambiado: Usuario en lugar de dict
):
    """Abre una casilla en el juego de minas"""
    juego = sesiones_activas.get(session_id)
    if not juego:
        raise HTTPException(status_code=404, detail="Sesión de juego no encontrada o expirada")
    
    if juego.usuario_id != current_user.id:  # Cambiado: current_user.id
        raise HTTPException(status_code=403, detail="No tienes permiso para este juego")
    
    try:
        user = db.query(Usuario).filter(Usuario.id == current_user.id).first()  # Cambiado: current_user.id
        
        resultado = juego.abrir_casilla(x, y)
        
        if resultado["game_over"]:
            if resultado["ganado"]:
                # Pagar ganancia al usuario
                ganancia = resultado["ganancia"]
                user.saldo += ganancia
                
                # Registrar en historial
                try:
                    from ...models.historial import HistorialJuego  # Ajusta según tu modelo
                    historial = HistorialJuego(
                        usuario_id=user.id,
                        juego="minas",
                        resultado="ganado",
                        apuesta=juego.apuesta,
                        ganancia=ganancia,
                        multiplicador=juego.multiplicador_actual,
                        dificultad=juego.dificultad,
                        detalles=json.dumps({
                            "casillas_abiertas": len(juego.casillas_abiertas),
                            "minas_totales": juego.minas_totales,
                            "session_id": session_id
                        })
                    )
                    db.add(historial)
                    db.commit()
                
                except Exception as e:
                    print(f"⚠️ Error al registrar historial: {e}")
                    db.commit()  # Aún así commit los cambios de saldo
                
                # Eliminar sesión
                del sesiones_activas[session_id]
                
                return {
                    "success": True,
                    **resultado,
                    "nuevo_saldo": user.saldo,
                    "tablero_completo": juego.tablero,
                    "casillas_abiertas": [(c[0], c[1], juego.tablero[c[0]][c[1]]["minas_cercanas"]) for c in juego.casillas_abiertas]
                }
            elif resultado["es_mine"]:
                # Registrar pérdida
                try:
                    from ...models.historial import HistorialJuego
                    historial = HistorialJuego(
                        usuario_id=user.id,
                        juego="minas",
                        resultado="perdido",
                        apuesta=juego.apuesta,
                        ganancia=0,
                        multiplicador=1.0,
                        dificultad=juego.dificultad,
                        detalles=json.dumps({
                            "casillas_abiertas": len(juego.casillas_abiertas),
                            "minas_totales": juego.minas_totales,
                            "session_id": session_id,
                            "mina_en": {"x": x, "y": y}
                        })
                    )
                    db.add(historial)
                    db.commit()
                except Exception as e:
                    print(f"⚠️ Error al registrar historial: {e}")
                    db.commit()
                
                # Mostrar todas las minas
                for i in range(juego.tamano):
                    for j in range(juego.tamano):
                        if juego.tablero[i][j]["es_mine"]:
                            juego.tablero[i][j]["abierta"] = True
                
                # Eliminar sesión
                del sesiones_activas[session_id]
                
                return {
                    "success": True,
                    **resultado,
                    "nuevo_saldo": user.saldo,
                    "tablero_completo": juego.tablero,
                    "casillas_abiertas": [(c[0], c[1], juego.tablero[c[0]][c[1]]["minas_cercanas"]) for c in juego.casillas_abiertas]
                }
        else:
            # Juego aún activo
            casillas_con_info = []
            for cx, cy in juego.casillas_abiertas:
                casilla = juego.tablero[cx][cy]
                casillas_con_info.append({
                    "x": cx,
                    "y": cy,
                    "minas_cercanas": casilla["minas_cercanas"]
                })
            
            db.commit()
            
            return {
                "success": True,
                **resultado,
                "nuevo_saldo": user.saldo,
                "casillas_abiertas": casillas_con_info,
                "casillas_marcadas": juego.casillas_marcadas,
                "minas_restantes": juego.minas_totales - len(juego.casillas_marcadas),
                "multiplicador_actual": juego.multiplicador_actual,
                "ganancia_potencial": juego.ganancia_actual,
                "mensaje": f"Casilla segura. Multiplicador actual: {juego.multiplicador_actual:.2f}x"
            }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")

@router.post("/{session_id}/marcar")
def marcar_casilla(
    session_id: str,
    x: int,
    y: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)  # Cambiado: Usuario en lugar de dict
):
    """Marca/desmarca una casilla con bandera"""
    juego = sesiones_activas.get(session_id)
    if not juego:
        raise HTTPException(status_code=404, detail="Sesión de juego no encontrada")
    
    if juego.usuario_id != current_user.id:  # Cambiado: current_user.id
        raise HTTPException(status_code=403, detail="No tienes permiso para este juego")
    
    try:
        marcada = juego.marcar_casilla(x, y)
        
        return {
            "success": True,
            "marcada": marcada,
            "minas_restantes": juego.minas_totales - len(juego.casillas_marcadas),
            "casillas_marcadas": juego.casillas_marcadas
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/{session_id}/retirarse")
def retirarse_minas(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)  # Cambiado: Usuario en lugar de dict
):
    """El jugador se retira del juego y cobra su ganancia"""
    juego = sesiones_activas.get(session_id)
    if not juego:
        raise HTTPException(status_code=404, detail="Sesión de juego no encontrada")
    
    if juego.usuario_id != current_user.id:  # Cambiado: current_user.id
        raise HTTPException(status_code=403, detail="No tienes permiso para este juego")
    
    if juego.game_over:
        raise HTTPException(status_code=400, detail="El juego ya ha terminado")
    
    user = db.query(Usuario).filter(Usuario.id == current_user.id).first()  # Cambiado: current_user.id
    
    try:
        # Calcular ganancia por retiro
        ganancia = juego.retirarse()
        user.saldo += ganancia
        
        # Registrar en historial
        try:
            from ...models.historial import HistorialJuego
            historial = HistorialJuego(
                usuario_id=user.id,
                juego="minas",
                resultado="retirado",
                apuesta=juego.apuesta,
                ganancia=ganancia,
                multiplicador=juego.multiplicador_actual,
                dificultad=juego.dificultad,
                detalles=json.dumps({
                    "casillas_abiertas": len(juego.casillas_abiertas),
                    "minas_totales": juego.minas_totales,
                    "session_id": session_id
                })
            )
            db.add(historial)
            db.commit()
            db.refresh(user)
        except Exception as e:
            print(f"⚠️ Error al registrar historial: {e}")
            db.commit()
            db.refresh(user)
        
        # Eliminar sesión
        del sesiones_activas[session_id]
        
        return {
            "success": True,
            "ganancia": ganancia,
            "nuevo_saldo": user.saldo,
            "casillas_abiertas": len(juego.casillas_abiertas),
            "multiplicador_final": juego.multiplicador_actual,
            "mensaje": f"Te retiraste con ${ganancia} de ganancia (Multiplicador: {juego.multiplicador_actual:.2f}x)"
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al retirarse: {str(e)}")

@router.delete("/{session_id}")
def cancelar_juego(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)  # Cambiado: Usuario en lugar de dict
):
    """Cancela un juego activo (sin ganancia)"""
    juego = sesiones_activas.get(session_id)
    if not juego:
        raise HTTPException(status_code=404, detail="Sesión de juego no encontrada")
    
    if juego.usuario_id != current_user.id:  # Cambiado: current_user.id
        raise HTTPException(status_code=403, detail="No tienes permiso para este juego")
    
    # No devolver dinero al cancelar (ya se descontó al iniciar)
    # Eliminar sesión
    del sesiones_activas[session_id]
    
    return {
        "success": True,
        "mensaje": "Juego cancelado",
        "perdida": juego.apuesta
    }

@router.get("/{session_id}/estado")
def obtener_estado(
    session_id: str,
    current_user: Usuario = Depends(get_current_user)  # Cambiado: Usuario en lugar de dict
):
    """Obtiene el estado actual del juego"""
    juego = sesiones_activas.get(session_id)
    if not juego:
        raise HTTPException(status_code=404, detail="Sesión de juego no encontrada")
    
    if juego.usuario_id != current_user.id:  # Cambiado: current_user.id
        raise HTTPException(status_code=403, detail="No tienes permiso para este juego")
    
    return {
        "success": True,
        **juego.obtener_estado()
    }

@router.get("/config")
def get_config_minas():
    """Obtiene la configuración del juego de minas"""
    return {
        "success": True,
        "dificultades": MINAS_CONFIG,
        "apuestas_permitidas": [100, 500, 1000, 2000, 5000, 10000],
        "instrucciones": {
            "objetivo": "Abrir todas las casillas seguras sin tocar minas",
            "multiplicador": "Aumenta con cada casilla segura abierta",
            "retiro": "Puedes retirarte en cualquier momento y llevarte la ganancia actual",
            "marcado": "Usa click derecho para marcar casillas sospechosas"
        }
    }

@router.get("/sesiones-activas")
def listar_sesiones_activas(current_user: Usuario = Depends(get_current_user)):  # Cambiado: Usuario en lugar de dict
    """Lista las sesiones activas del usuario"""
    sesiones_usuario = []
    for juego_id, juego in sesiones_activas.items():
        if juego.usuario_id == current_user.id:  # Cambiado: current_user.id
            sesiones_usuario.append(juego.obtener_estado())
    
    return {
        "success": True,
        "sesiones": sesiones_usuario,
        "total": len(sesiones_usuario)
    }

@router.get("/test")
def test_endpoint():
    """Endpoint de prueba para verificar que el servidor funciona"""
    return {
        "success": True,
        "message": "Servidor de Minas funcionando correctamente",
        "sesiones_activas": len(sesiones_activas)
    }

@router.get("/health")
async def health_check():
    """Endpoint de salud para verificar que el servidor está vivo"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "sesiones_activas": len(sesiones_activas)
    }