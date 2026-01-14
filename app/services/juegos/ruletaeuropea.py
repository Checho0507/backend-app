from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import random
from typing import Dict, List
from ...database import get_db
from ...api.auth import get_current_user
from ...models.usuario import Usuario

router = APIRouter()

# Configuración de la ruleta europea (un solo cero)
NUMEROS_RULETA = list(range(0, 37))  # 0 al 36

# Colores de los números (0 es verde)
COLORES = {
    0: "verde",
    32: "rojo", 15: "negro", 19: "rojo", 4: "negro", 21: "rojo", 2: "negro", 25: "rojo", 17: "negro",
    34: "rojo", 6: "negro", 27: "rojo", 13: "negro", 36: "rojo", 11: "negro", 30: "rojo", 8: "negro",
    23: "rojo", 10: "negro", 5: "rojo", 24: "negro", 16: "rojo", 33: "negro", 1: "rojo", 20: "negro",
    14: "rojo", 31: "negro", 9: "rojo", 22: "negro", 18: "rojo", 29: "negro", 7: "rojo", 28: "negro",
    12: "rojo", 35: "negro", 3: "rojo", 26: "negro"
}

# Tipos de apuestas y sus multiplicadores
TIPOS_APUESTA = {
    "numero_pleno": {"multiplicador": 35, "descripcion": "Apuesta a un número exacto"},
    "docena": {"multiplicador": 2, "descripcion": "Apuesta a una docena (1-12, 13-24, 25-36)"},
    "columna": {"multiplicador": 2, "descripcion": "Apuesta a una columna"},
    "rojo_negro": {"multipliccionador": 2, "descripcion": "Apuesta a color rojo o negro"},
    "par_impar": {"multiplicador": 2, "descripcion": "Apuesta a par o impar"},
    "bajo_alto": {"multiplicador": 2, "descripcion": "Apuesta a bajo (1-18) o alto (19-36)"}
}

class RuletaEuropea:
    def __init__(self):
        self.numeros = NUMEROS_RULETA
        self.colores = COLORES
        
    def girar(self):
        """Gira la ruleta y devuelve un número aleatorio"""
        return random.choice(self.numeros)
    
    def obtener_color(self, numero: int) -> str:
        """Devuelve el color de un número"""
        return self.colores.get(numero, "verde")
    
    def es_par(self, numero: int) -> bool:
        """Verifica si un número es par (0 no es par ni impar)"""
        if numero == 0:
            return False
        return numero % 2 == 0
    
    def es_impar(self, numero: int) -> bool:
        """Verifica si un número es impar (0 no es par ni impar)"""
        if numero == 0:
            return False
        return numero % 2 == 1
    
    def es_bajo(self, numero: int) -> bool:
        """Verifica si un número es bajo (1-18)"""
        return 1 <= numero <= 18
    
    def es_alto(self, numero: int) -> bool:
        """Verifica si un número es alto (19-36)"""
        return 19 <= numero <= 36
    
    def obtener_docena(self, numero: int) -> int:
        """Devuelve la docena a la que pertenece un número (1, 2 o 3)"""
        if numero == 0:
            return 0
        elif 1 <= numero <= 12:
            return 1
        elif 13 <= numero <= 24:
            return 2
        else:
            return 3
    
    def obtener_columna(self, numero: int) -> int:
        """Devuelve la columna a la que pertenece un número (1, 2 o 3)"""
        if numero == 0:
            return 0
        
        # Columnas de la ruleta europea:
        # Columna 1: 1, 4, 7, 10, 13, 16, 19, 22, 25, 28, 31, 34
        # Columna 2: 2, 5, 8, 11, 14, 17, 20, 23, 26, 29, 32, 35
        # Columna 3: 3, 6, 9, 12, 15, 18, 21, 24, 27, 30, 33, 36
        
        columna_1 = [1, 4, 7, 10, 13, 16, 19, 22, 25, 28, 31, 34]
        columna_2 = [2, 5, 8, 11, 14, 17, 20, 23, 26, 29, 32, 35]
        columna_3 = [3, 6, 9, 12, 15, 18, 21, 24, 27, 30, 33, 36]
        
        if numero in columna_1:
            return 1
        elif numero in columna_2:
            return 2
        elif numero in columna_3:
            return 3
        else:
            return 0

ruleta = RuletaEuropea()

@router.post("/juegos/ruletaeuropea")
def jugar_ruleta_europea(
    apuestas: Dict[str, Dict],  # {tipo_apuesta: {"valor": ..., "monto": ...}}
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    """
    Juego de Ruleta Europea.
    El usuario puede realizar múltiples apuestas en una jugada.
    """
    
    # Recargar el usuario en la sesión actual
    user = db.query(Usuario).filter(Usuario.id == current_user.id).first()

    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    # Validar que haya apuestas
    if not apuestas or len(apuestas) == 0:
        raise HTTPException(status_code=400, detail="Debes realizar al menos una apuesta")
    
    # Calcular el total apostado
    total_apostado = sum(apuesta["monto"] for apuesta in apuestas.values())
    
    # Validar apuesta mínima por tipo (puede variar según casino, usamos 10 como mínimo general)
    for tipo, datos in apuestas.items():
        if datos["monto"] < 10:
            raise HTTPException(
                status_code=400, 
                detail=f"La apuesta mínima para {tipo} es $10"
            )
    
    # Validar saldo
    if user.saldo < total_apostado:
        raise HTTPException(
            status_code=400, 
            detail=f"Saldo insuficiente. Necesitas ${total_apostado} para apostar."
        )
    
    # Descontar el total apostado
    user.saldo -= total_apostado
    
    # Girar la ruleta
    numero_ganador = ruleta.girar()
    color_ganador = ruleta.obtener_color(numero_ganador)
    
    # Calcular ganancias
    ganancia_total = 0
    apuestas_ganadoras = []
    apuestas_perdedoras = []
    
    for tipo_apuesta, datos_apuesta in apuestas.items():
        monto = datos_apuesta["monto"]
        valor_apuesta = datos_apuesta.get("valor")
        gano = False
        ganancia = 0
        
        # Verificar si la apuesta ganó según el tipo
        if tipo_apuesta == "numero_pleno":
            if valor_apuesta == numero_ganador:
                gano = True
                ganancia = monto * TIPOS_APUESTA[tipo_apuesta]["multiplicador"]
        
        elif tipo_apuesta == "rojo_negro":
            if color_ganador == valor_apuesta and numero_ganador != 0:
                gano = True
                ganancia = monto * TIPOS_APUESTA[tipo_apuesta]["multiplicador"]
        
        elif tipo_apuesta == "par_impar":
            if valor_apuesta == "par" and ruleta.es_par(numero_ganador):
                gano = True
                ganancia = monto * TIPOS_APUESTA[tipo_apuesta]["multiplicador"]
            elif valor_apuesta == "impar" and ruleta.es_impar(numero_ganador):
                gano = True
                ganancia = monto * TIPOS_APUESTA[tipo_apuesta]["multiplicador"]
        
        elif tipo_apuesta == "bajo_alto":
            if valor_apuesta == "bajo" and ruleta.es_bajo(numero_ganador):
                gano = True
                ganancia = monto * TIPOS_APUESTA[tipo_apuesta]["multiplicador"]
            elif valor_apuesta == "alto" and ruleta.es_alto(numero_ganador):
                gano = True
                ganancia = monto * TIPOS_APUESTA[tipo_apuesta]["multiplicador"]
        
        elif tipo_apuesta == "docena":
            docena_ganadora = ruleta.obtener_docena(numero_ganador)
            if valor_apuesta == docena_ganadora:
                gano = True
                ganancia = monto * TIPOS_APUESTA[tipo_apuesta]["multiplicador"]
        
        elif tipo_apuesta == "columna":
            columna_ganadora = ruleta.obtener_columna(numero_ganador)
            if valor_apuesta == columna_ganadora:
                gano = True
                ganancia = monto * TIPOS_APUESTA[tipo_apuesta]["multiplicador"]
        
        # Para apuestas múltiples (split, calle, esquina, linea)
        elif tipo_apuesta in ["split", "calle", "esquina", "linea"]:
            # valor_apuesta sería una lista de números
            if numero_ganador in valor_apuesta:
                gano = True
                ganancia = monto * TIPOS_APUESTA[tipo_apuesta]["multiplicador"]
        
        # Registrar resultado de la apuesta
        if gano:
            apuestas_ganadoras.append({
                "tipo": tipo_apuesta,
                "valor": valor_apuesta,
                "monto": monto,
                "ganancia": ganancia
            })
            ganancia_total += ganancia
        else:
            apuestas_perdedoras.append({
                "tipo": tipo_apuesta,
                "valor": valor_apuesta,
                "monto": monto,
                "ganancia": 0
            })
    
    # Sumar ganancias al saldo
    user.saldo += ganancia_total
    
    db.commit()
    db.refresh(user)
    
    return {
        "numero_ganador": numero_ganador,
        "color_ganador": color_ganador,
        "es_par": ruleta.es_par(numero_ganador),
        "es_impar": ruleta.es_impar(numero_ganador),
        "es_bajo": ruleta.es_bajo(numero_ganador),
        "es_alto": ruleta.es_alto(numero_ganador),
        "docena": ruleta.obtener_docena(numero_ganador),
        "columna": ruleta.obtener_columna(numero_ganador),
        "total_apostado": total_apostado,
        "ganancia_total": ganancia_total,
        "nuevo_saldo": user.saldo,
        "apuestas_ganadoras": apuestas_ganadoras,
        "apuestas_perdedoras": apuestas_perdedoras,
        "mensaje": f"¡Número ganador: {numero_ganador} {color_ganador.upper()}!"
    }

@router.get("/juegos/ruletaeuropea/probabilidades")
def obtener_probabilidades():
    """
    Devuelve las probabilidades de la ruleta europea
    """
    total_numeros = len(NUMEROS_RULETA)
    probabilidades = {}
    multiplicadores = {}
    
    # Calcular probabilidades para cada tipo de apuesta
    for tipo, info in TIPOS_APUESTA.items():
        if tipo == "numero_pleno":
            probabilidad = 1 / total_numeros * 100
            multiplicadores[tipo] = 35
        elif tipo in ["docena", "columna"]:
            probabilidad = 12 / total_numeros * 100
            multiplicadores[tipo] = 2
        elif tipo in ["rojo_negro", "par_impar", "bajo_alto"]:
            probabilidad = 18 / total_numeros * 100
            multiplicadores[tipo] = 2
        else:
            probabilidad = 0
        
        probabilidades[tipo] = {
            "probabilidad": round(probabilidad, 2),
            "multiplicador": multiplicadores[tipo],
            "descripcion": info["descripcion"]
        }
    
    return {
        "probabilidades": probabilidades,
        "numeros_totales": total_numeros,
        "ventaja_casa": round(1 / total_numeros * 100, 2)  # 2.70% en ruleta europea
    }