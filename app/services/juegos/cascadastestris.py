import random
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Dict, Tuple, Optional
from ...database import get_db
from ...api.auth import get_current_user
from ...models.usuario import Usuario

router = APIRouter()

# Configuraciones del juego
CONFIGURACIONES = {
    "5x5": {
        "filas": 5,
        "columnas": 5,
        "multiplicador_base": 1.0,
        "apuesta_minima": 100,
        "apuesta_maxima": 5000
    },
    "10x10": {
        "filas": 10,
        "columnas": 10,
        "multiplicador_base": 2.0,  # Doble premio por ser más difícil
        "apuesta_minima": 500,
        "apuesta_maxima": 20000
    }
}

# Símbolos con pesos y colores para el frontend
SIMBOLOS = {
    "🔴": {"peso": 30, "color": "red", "grupo": 1},
    "🔵": {"peso": 30, "color": "blue", "grupo": 2},
    "🟢": {"peso": 30, "color": "green", "grupo": 3},
    "🟡": {"peso": 20, "color": "yellow", "grupo": 4},
    "🟣": {"peso": 15, "color": "purple", "grupo": 5},
    "🟠": {"peso": 10, "color": "orange", "grupo": 6},
    "💎": {"peso": 5, "color": "cyan", "grupo": 7},
    "⭐": {"peso": 2, "color": "gold", "grupo": 8},
    "👑": {"peso": 1, "color": "pink", "grupo": 9}
}

# Multiplicadores por cantidad de elementos en combinación
MULTIPLICADORES_COMBO = {
    3: 1,
    4: 2,
    5: 5,
    6: 10,
    7: 25,
    8: 50,
    9: 100,
    10: 200
}

# Bonus por explosiones en cascada
BONUS_CASCADA = {
    1: 1.0,
    2: 1.2,
    3: 1.5,
    4: 2.0,
    5: 3.0,
    6: 5.0
}

def generar_matriz(filas: int, columnas: int) -> List[List[str]]:
    """Genera una matriz aleatoria de símbolos"""
    simbolos_lista = list(SIMBOLOS.keys())
    pesos = [SIMBOLOS[s]["peso"] for s in simbolos_lista]
    
    matriz = []
    for _ in range(filas):
        fila = random.choices(simbolos_lista, weights=pesos, k=columnas)
        matriz.append(fila)
    return matriz

def encontrar_combinaciones(matriz: List[List[str]], min_combo: int = 3) -> List[Dict]:
    """Encuentra combinaciones horizontales, verticales y diagonales"""
    filas = len(matriz)
    columnas = len(matriz[0])
    combinaciones = []
    
    # Combinaciones horizontales
    for fila in range(filas):
        col = 0
        while col < columnas:
            simbolo = matriz[fila][col]
            if simbolo == "":  # Celda vacía
                col += 1
                continue
                
            longitud = 1
            while col + longitud < columnas and matriz[fila][col + longitud] == simbolo:
                longitud += 1
            
            if longitud >= min_combo:
                combinaciones.append({
                    "tipo": "horizontal",
                    "simbolo": simbolo,
                    "posiciones": [(fila, col + i) for i in range(longitud)],
                    "longitud": longitud
                })
            col += longitud
    
    # Combinaciones verticales
    for col in range(columnas):
        fila = 0
        while fila < filas:
            simbolo = matriz[fila][col]
            if simbolo == "":
                fila += 1
                continue
                
            longitud = 1
            while fila + longitud < filas and matriz[fila + longitud][col] == simbolo:
                longitud += 1
            
            if longitud >= min_combo:
                combinaciones.append({
                    "tipo": "vertical",
                    "simbolo": simbolo,
                    "posiciones": [(fila + i, col) for i in range(longitud)],
                    "longitud": longitud
                })
            fila += longitud
    
    # Combinaciones diagonales (abajo-derecha)
    for fila in range(filas - min_combo + 1):
        for col in range(columnas - min_combo + 1):
            simbolo = matriz[fila][col]
            if simbolo == "":
                continue
                
            longitud = 1
            while (fila + longitud < filas and 
                   col + longitud < columnas and 
                   matriz[fila + longitud][col + longitud] == simbolo):
                longitud += 1
            
            if longitud >= min_combo:
                combinaciones.append({
                    "tipo": "diagonal_desc",
                    "simbolo": simbolo,
                    "posiciones": [(fila + i, col + i) for i in range(longitud)],
                    "longitud": longitud
                })
    
    # Combinaciones diagonales (arriba-derecha)
    for fila in range(min_combo - 1, filas):
        for col in range(columnas - min_combo + 1):
            simbolo = matriz[fila][col]
            if simbolo == "":
                continue
                
            longitud = 1
            while (fila - longitud >= 0 and 
                   col + longitud < columnas and 
                   matriz[fila - longitud][col + longitud] == simbolo):
                longitud += 1
            
            if longitud >= min_combo:
                combinaciones.append({
                    "tipo": "diagonal_asc",
                    "simbolo": simbolo,
                    "posiciones": [(fila - i, col + i) for i in range(longitud)],
                    "longitud": longitud
                })
    
    return combinaciones

def eliminar_combinaciones(matriz: List[List[str]], combinaciones: List[Dict]) -> Tuple[List[List[str]], List[Tuple[int, int]]]:
    """Elimina los símbolos en combinaciones y devuelve posiciones eliminadas"""
    posiciones_eliminadas = []
    for combo in combinaciones:
        for fila, col in combo["posiciones"]:
            if matriz[fila][col] != "":
                matriz[fila][col] = ""
                posiciones_eliminadas.append((fila, col))
    
    # Eliminar duplicados (por si una celda está en múltiples combinaciones)
    posiciones_eliminadas = list(set(posiciones_eliminadas))
    return matriz, posiciones_eliminadas

def aplicar_gravedad(matriz: List[List[str]]) -> Tuple[List[List[str]], List[Dict]]:
    """Aplica gravedad para que los símbolos caigan y genera nuevos en la parte superior"""
    filas = len(matriz)
    columnas = len(matriz[0])
    movimientos = []
    
    for col in range(columnas):
        # Mover símbolos hacia abajo
        pos_vacia = filas - 1
        for fila in range(filas - 1, -1, -1):
            if matriz[fila][col] != "":
                if pos_vacia != fila:
                    matriz[pos_vacia][col] = matriz[fila][col]
                    matriz[fila][col] = ""
                    movimientos.append({
                        "desde": (fila, col),
                        "hacia": (pos_vacia, col),
                        "simbolo": matriz[pos_vacia][col]
                    })
                pos_vacia -= 1
        
        # Generar nuevos símbolos en la parte superior
        simbolos_lista = list(SIMBOLOS.keys())
        pesos = [SIMBOLOS[s]["peso"] for s in simbolos_lista]
        
        for fila in range(pos_vacia, -1, -1):
            nuevo_simbolo = random.choices(simbolos_lista, weights=pesos, k=1)[0]
            matriz[fila][col] = nuevo_simbolo
            movimientos.append({
                "desde": None,
                "hacia": (fila, col),
                "simbolo": nuevo_simbolo,
                "nuevo": True
            })
    
    return matriz, movimientos

def calcular_puntaje(combinaciones: List[Dict], apuesta: float, multiplicador_base: float, nivel_cascada: int) -> Dict:
    """Calcula el puntaje total de las combinaciones"""
    puntaje_total = 0
    detalles = []
    
    for combo in combinaciones:
        multiplicador_combo = MULTIPLICADORES_COMBO.get(combo["longitud"], 1)
        grupo = SIMBOLOS[combo["simbolo"]]["grupo"]
        base_puntaje = grupo * 10  # Puntaje base según grupo (1-9)
        
        puntaje_combo = base_puntaje * multiplicador_combo * multiplicador_base
        puntaje_total += puntaje_combo
        
        detalles.append({
            "simbolo": combo["simbolo"],
            "tipo": combo["tipo"],
            "longitud": combo["longitud"],
            "cantidad": len(combo["posiciones"]),
            "grupo": grupo,
            "multiplicador": multiplicador_combo,
            "puntaje": puntaje_combo,
            "posiciones": combo["posiciones"]
        })
    
    # Aplicar bonus por cascada
    bonus = BONUS_CASCADA.get(min(nivel_cascada, 6), 1.0)
    puntaje_total *= bonus
    
    # Convertir a ganancia monetaria
    ganancia = puntaje_total * apuesta / 100
    
    return {
        "puntaje_total": puntaje_total,
        "ganancia": ganancia,
        "bonus_cascada": bonus,
        "nivel_cascada": nivel_cascada,
        "detalles": detalles,
        "multiplicador_total": puntaje_total / 100 * bonus
    }

@router.get("/juegos/cascadas/configuraciones")
def obtener_configuraciones():
    """Endpoint para obtener las configuraciones disponibles"""
    configs = {}
    for nombre, config in CONFIGURACIONES.items():
        configs[nombre] = {
            "filas": config["filas"],
            "columnas": config["columnas"],
            "apuesta_minima": config["apuesta_minima"],
            "apuesta_maxima": config["apuesta_maxima"],
            "multiplicador_base": config["multiplicador_base"]
        }
    
    return {
        "configuraciones": configs,
        "simbolos": SIMBOLOS,
        "multiplicadores_combo": MULTIPLICADORES_COMBO,
        "bonus_cascada": BONUS_CASCADA
    }

@router.post("/juegos/cascadas")
def jugar_cascadas(
    configuracion: str = Query(..., description="Configuración (5x5 o 10x10)"),
    apuesta: int = Query(..., description="Monto de la apuesta"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    # Validar configuración
    if configuracion not in CONFIGURACIONES:
        raise HTTPException(
            status_code=400, 
            detail=f"Configuración no válida. Opciones: {list(CONFIGURACIONES.keys())}"
        )
    
    config = CONFIGURACIONES[configuracion]
    
    # Validar apuesta
    if apuesta < config["apuesta_minima"] or apuesta > config["apuesta_maxima"]:
        raise HTTPException(
            status_code=400,
            detail=f"Apuesta no válida para {configuracion}. Mínimo: ${config['apuesta_minima']}, Máximo: ${config['apuesta_maxima']}"
        )

    usuario = db.query(Usuario).filter(Usuario.id == current_user.id).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if usuario.saldo < apuesta:
        raise HTTPException(status_code=400, detail="Saldo insuficiente para apostar")

    # Descontar la apuesta
    usuario.saldo -= apuesta

    # Generar matriz inicial
    matriz = generar_matriz(config["filas"], config["columnas"])
    
    # Proceso de cascada
    cascadas = []
    nivel_cascada = 0
    ganancia_total = 0
    todas_combinaciones = []
    
    while True:
        # Encontrar combinaciones
        combinaciones = encontrar_combinaciones(matriz)
        
        if not combinaciones:
            break
        
        nivel_cascada += 1
        
        # Calcular puntaje de esta cascada
        resultado_cascada = calcular_puntaje(
            combinaciones, 
            apuesta, 
            config["multiplicador_base"],
            nivel_cascada
        )
        
        ganancia_total += resultado_cascada["ganancia"]
        todas_combinaciones.extend(combinaciones)
        
        # Registrar cascada
        cascada_info = {
            "nivel": nivel_cascada,
            "combinaciones_encontradas": len(combinaciones),
            "simbolos_eliminados": sum(len(c["posiciones"]) for c in combinaciones),
            "puntaje": resultado_cascada["puntaje_total"],
            "ganancia": resultado_cascada["ganancia"],
            "bonus": resultado_cascada["bonus_cascada"],
            "detalles": resultado_cascada["detalles"]
        }
        cascadas.append(cascada_info)
        
        # Eliminar combinaciones
        matriz, _ = eliminar_combinaciones(matriz, combinaciones)
        
        # Aplicar gravedad
        matriz, movimientos = aplicar_gravedad(matriz)
        cascada_info["movimientos"] = movimientos
        
        # Copiar matriz para mostrar el estado después de la caída
        cascada_info["matriz_despues"] = [fila.copy() for fila in matriz]
    
    # Añadir ganancia total al saldo
    usuario.saldo += ganancia_total

    # Preparar respuesta
    if ganancia_total > 0:
        if nivel_cascada > 1:
            mensaje = f"🎉 ¡CASCADA DE {nivel_cascada} NIVELES! Ganancia total: ${ganancia_total:,.2f}"
        else:
            mensaje = f"🎉 ¡COMBINACIÓN! Ganancia: ${ganancia_total:,.2f}"
    else:
        mensaje = "❌ Sin combinaciones esta vez. ¡Inténtalo de nuevo!"

    db.commit()
    db.refresh(usuario)

    return {
        "matriz_inicial": matriz if not cascadas else cascadas[0].get("matriz_despues", []),
        "cascadas": cascadas,
        "ganancia_total": ganancia_total,
        "nuevo_saldo": usuario.saldo,
        "mensaje": mensaje,
        "apuesta": apuesta,
        "configuracion": configuracion,
        "niveles_cascada": nivel_cascada,
        "total_combinaciones": len(todas_combinaciones),
        "multiplicador_base": config["multiplicador_base"],
        "resumen": {
            "ganancia_bruta": ganancia_total,
            "ganancia_neta": ganancia_total - apuesta,
            "roi": ((ganancia_total - apuesta) / apuesta * 100) if apuesta > 0 else 0
        }
    }

@router.get("/juegos/cascadas/simular")
def simular_cascada(
    configuracion: str = Query("5x5", description="Configuración a simular"),
    pasos: int = Query(3, description="Número de pasos a simular")
):
    """Endpoint para simular una cascada (sin apostar)"""
    if configuracion not in CONFIGURACIONES:
        raise HTTPException(status_code=400, detail="Configuración no válida")
    
    config = CONFIGURACIONES[configuracion]
    matriz = generar_matriz(config["filas"], config["columnas"])
    
    simulacion = {
        "matriz_inicial": [fila.copy() for fila in matriz],
        "pasos": []
    }
    
    for paso in range(min(pasos, 5)):  # Máximo 5 pasos para no sobrecargar
        combinaciones = encontrar_combinaciones(matriz)
        
        if not combinaciones:
            break
        
        paso_info = {
            "paso": paso + 1,
            "combinaciones": len(combinaciones),
            "simbolos_eliminados": sum(len(c["posiciones"]) for c in combinaciones),
            "detalles": []
        }
        
        for combo in combinaciones[:3]:  # Mostrar solo primeras 3 combinaciones
            paso_info["detalles"].append({
                "simbolo": combo["simbolo"],
                "tipo": combo["tipo"],
                "longitud": combo["longitud"],
                "posiciones": combo["posiciones"][:5]  # Mostrar solo primeras 5 posiciones
            })
        
        # Eliminar y aplicar gravedad
        matriz, _ = eliminar_combinaciones(matriz, combinaciones)
        matriz, movimientos = aplicar_gravedad(matriz)
        
        paso_info["movimientos"] = len(movimientos)
        paso_info["matriz_despues"] = [fila.copy() for fila in matriz]
        
        simulacion["pasos"].append(paso_info)
    
    return simulacion