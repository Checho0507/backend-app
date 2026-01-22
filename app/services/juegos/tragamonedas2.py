import random
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Dict, Tuple
from ...database import get_db
from ...api.auth import get_current_user
from ...models.usuario import Usuario

router = APIRouter()

# Configuración del juego 2.0
REELS = 5  # Número de columnas
ROWS = 3   # Número de filas

# Símbolos disponibles con pesos (probabilidades)
SIMBOLOS_CON_PESO = {
    "🍒": 40,    # Muy común
    "🍋": 35,    # Común
    "🍊": 30,    # Común
    "🍉": 25,    # Medio
    "⭐": 20,     # Medio
    "🔔": 15,     # Raro
    "🍇": 10,     # Raro
    "7️⃣": 5,      # Muy raro
    "💎": 2,      # Extremadamente raro
    "👑": 1       # Ultra raro
}

SIMBOLOS = list(SIMBOLOS_CON_PESO.keys())
PESOS = list(SIMBOLOS_CON_PESO.values())

# Tabla de pagos por símbolo y cantidad consecutiva
TABLA_PAGOS = {
    "👑": {3: 200, 4: 500, 5: 1000},  # Mega jackpot
    "💎": {3: 100, 4: 200, 5: 500},
    "7️⃣": {3: 50, 4: 100, 5: 200},
    "🍇": {3: 30, 4: 60, 5: 120},
    "🔔": {3: 20, 4: 40, 5: 80},
    "⭐": {3: 10, 4: 20, 5: 40},
    "🍉": {3: 5, 4: 10, 5: 20},
    "🍊": {3: 3, 4: 6, 5: 12},
    "🍋": {3: 2, 4: 4, 5: 8},
    "🍒": {3: 1, 4: 2, 5: 4}
}

# Líneas de pago (cada línea es una lista de (columna, fila) para 5x3)
LINEAS_DE_PAGO = [
    # Líneas horizontales
    [(0, 0), (1, 0), (2, 0), (3, 0), (4, 0)],  # Línea 1 - Fila superior
    [(0, 1), (1, 1), (2, 1), (3, 1), (4, 1)],  # Línea 2 - Fila central
    [(0, 2), (1, 2), (2, 2), (3, 2), (4, 2)],  # Línea 3 - Fila inferior
    
    # Líneas en V
    [(0, 0), (1, 1), (2, 2), (3, 1), (4, 0)],  # Línea 4 - V descendente
    [(0, 2), (1, 1), (2, 0), (3, 1), (4, 2)],  # Línea 5 - V ascendente
    
    # Líneas diagonales
    [(0, 0), (1, 0), (2, 1), (3, 2), (4, 2)],  # Línea 6
    [(0, 2), (1, 2), (2, 1), (3, 0), (4, 0)],  # Línea 7
    
    # Líneas en zigzag
    [(0, 1), (1, 0), (2, 1), (3, 0), (4, 1)],  # Línea 8
    [(0, 1), (1, 2), (2, 1), (3, 2), (4, 1)],  # Línea 9
    
    # Línea recta central
    [(0, 1), (1, 0), (2, 2), (3, 0), (4, 1)],  # Línea 10
]

APUESTAS_PERMITIDAS = [100, 250, 500, 1000, 2500, 5000]

def generar_reels() -> List[List[str]]:
    """Genera una matriz de reels aleatorios"""
    reels = []
    for _ in range(REELS):
        columna = random.choices(SIMBOLOS, weights=PESOS, k=ROWS)
        reels.append(columna)
    return reels

def obtener_simbolos_en_linea(reels: List[List[str]], linea: List[Tuple[int, int]]) -> List[str]:
    """Obtiene los símbolos en una línea específica"""
    simbolos = []
    for col, row in linea:
        simbolos.append(reels[col][row])
    return simbolos

def evaluar_combinacion(simbolos: List[str]) -> Dict:
    """Evalúa una combinación de símbolos y devuelve el resultado"""
    if len(simbolos) < 3:
        return {"ganancia": 0, "longitud": 0, "simbolo": None}
    
    # Buscar secuencias consecutivas
    simbolo_actual = simbolos[0]
    longitud = 1
    
    for i in range(1, len(simbolos)):
        if simbolos[i] == simbolo_actual:
            longitud += 1
        else:
            # Si tenemos al menos 3 símbolos iguales consecutivos desde el inicio
            if longitud >= 3:
                break
            else:
                # Reiniciar con nuevo símbolo
                simbolo_actual = simbolos[i]
                longitud = 1
    
    # Solo pagamos si hay al menos 3 símbolos iguales consecutivos desde el inicio
    if longitud >= 3 and simbolo_actual in TABLA_PAGOS:
        # Asegurarnos de no exceder la longitud máxima pagable (5)
        longitud = min(longitud, 5)
        multiplicador = TABLA_PAGOS[simbolo_actual].get(longitud, 0)
        return {
            "ganancia": multiplicador,
            "longitud": longitud,
            "simbolo": simbolo_actual
        }
    
    return {"ganancia": 0, "longitud": 0, "simbolo": None}

@router.get("/juegos/tragamonedas2/apuestas-permitidas")
def obtener_apuestas_permitidas():
    """Endpoint para obtener las apuestas permitidas"""
    return {
        "apuestas_permitidas": APUESTAS_PERMITIDAS,
        "lineas_de_pago": len(LINEAS_DE_PAGO),
        "reels": REELS,
        "rows": ROWS
    }

@router.get("/juegos/tragamonedas2/estadisticas")
def obtener_estadisticas_tragamonedas2():
    """Endpoint para mostrar estadísticas del juego 2.0"""
    return {
        "simbolos_disponibles": SIMBOLOS,
        "pesos_simbolos": SIMBOLOS_CON_PESO,
        "tabla_pagos": TABLA_PAGOS,
        "apuestas_permitidas": APUESTAS_PERMITIDAS,
        "lineas_de_pago": len(LINEAS_DE_PAGO),
        "configuracion": f"{REELS}x{ROWS}",
        "lineas_definidas": LINEAS_DE_PAGO
    }

@router.post("/juegos/tragamonedas2")
def jugar_tragamonedas2(
    apuesta: int = Query(..., description="Monto de la apuesta por línea"),
    lineas_activas: int = Query(10, description="Número de líneas activas (1-10)"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    # Validaciones
    if apuesta not in APUESTAS_PERMITIDAS:
        raise HTTPException(
            status_code=400, 
            detail=f"Apuesta no válida. Apuestas permitidas: {APUESTAS_PERMITIDAS}"
        )
    
    if lineas_activas < 1 or lineas_activas > len(LINEAS_DE_PAGO):
        raise HTTPException(
            status_code=400,
            detail=f"Número de líneas debe estar entre 1 y {len(LINEAS_DE_PAGO)}"
        )

    usuario = db.query(Usuario).filter(Usuario.id == current_user.id).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    # Calcular apuesta total
    apuesta_total = apuesta * lineas_activas
    
    if usuario.saldo < apuesta_total:
        raise HTTPException(
            status_code=400, 
            detail=f"Saldo insuficiente. Necesitas ${apuesta_total:,} (${apuesta:,} x {lineas_activas} líneas)"
        )

    # Descontar la apuesta total
    usuario.saldo -= apuesta_total

    # Generar reels
    reels = generar_reels()
    
    # Evaluar cada línea activa
    resultados_lineas = []
    ganancia_total = 0
    lineas_ganadoras = []
    
    for i in range(lineas_activas):
        linea = LINEAS_DE_PAGO[i]
        simbolos = obtener_simbolos_en_linea(reels, linea)
        resultado = evaluar_combinacion(simbolos)
        
        if resultado["ganancia"] > 0:
            ganancia_linea = resultado["ganancia"] * apuesta
            ganancia_total += ganancia_linea
            
            lineas_ganadoras.append({
                "linea": i + 1,
                "simbolos": simbolos,
                "simbolo_ganador": resultado["simbolo"],
                "cantidad": resultado["longitud"],
                "multiplicador": resultado["ganancia"],
                "ganancia": ganancia_linea
            })
        
        resultados_lineas.append({
            "linea": i + 1,
            "simbolos": simbolos,
            "ganancia_linea": resultado["ganancia"] * apuesta if resultado["ganancia"] > 0 else 0
        })

    # Añadir ganancia total al saldo
    usuario.saldo += ganancia_total

    # Preparar mensaje
    if ganancia_total > 0:
        if len(lineas_ganadoras) == 1:
            linea = lineas_ganadoras[0]
            mensaje = f"🎉 ¡GANASTE! Línea {linea['linea']}: {linea['cantidad']}x {linea['simbolo_ganador']} - ${ganancia_total:,}"
        else:
            mensaje = f"🎉 ¡MULTIPLE GANANCIA! {len(lineas_ganadoras)} líneas ganadoras - Total: ${ganancia_total:,}"
    else:
        mensaje = "❌ Sin suerte esta vez. ¡Inténtalo de nuevo!"

    # Transponer reels para frontend (de columnas a filas)
    reels_transpuestos = []
    for row in range(ROWS):
        fila = []
        for col in range(REELS):
            fila.append(reels[col][row])
        reels_transpuestos.append(fila)

    db.commit()
    db.refresh(usuario)

    return {
        "reels": reels_transpuestos,  # Matriz 3x5
        "ganancia_total": ganancia_total,
        "nuevo_saldo": usuario.saldo,
        "mensaje": mensaje,
        "apuesta_por_linea": apuesta,
        "apuesta_total": apuesta_total,
        "lineas_activas": lineas_activas,
        "lineas_ganadoras": lineas_ganadoras,
        "total_lineas_ganadoras": len(lineas_ganadoras),
        "detalles_lineas": resultados_lineas,
        "configuracion": f"{REELS}x{ROWS}"
    }