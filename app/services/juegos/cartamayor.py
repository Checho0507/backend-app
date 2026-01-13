from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import random
from ...database import get_db
from ...api.auth import get_current_user
from ...models.usuario import Usuario

router = APIRouter()

APUESTA_MINIMA = 100
VALORES_CARTAS = {
    1: ("As", "A"),
    2: ("2", "2"),
    3: ("3", "3"),
    4: ("4", "4"),
    5: ("5", "5"),
    6: ("6", "6"),
    7: ("7", "7"),
    8: ("8", "8"),
    9: ("9", "9"),
    10: ("10", "10"),
    11: ("Jota", "J"),
    12: ("Reina", "Q"),
    13: ("Rey", "K")
}
PALOS = ["♠️", "♥️", "♦️", "♣️"]

@router.post("/juegos/cartamayor")
def jugar_carta_mayor(
    apuesta: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    """
    Juego de Carta Mayor.
    El usuario apuesta y se reparte una carta al usuario y otra a la casa.
    Gana el que tenga la carta más alta.
    Empate: devuelve la apuesta.
    Usuario gana: gana el doble (apuesta * 2).
    Casa gana: pierde la apuesta.
    """
    
    # Recargar el usuario en la sesión actual
    user = db.query(Usuario).filter(Usuario.id == current_user.id).first()

    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    # Validar apuesta mínima
    if apuesta < APUESTA_MINIMA:
        raise HTTPException(
            status_code=400, 
            detail=f"La apuesta mínima es ${APUESTA_MINIMA}"
        )

    # Validar saldo
    if user.saldo < apuesta:
        raise HTTPException(
            status_code=400, 
            detail=f"Saldo insuficiente. Necesitas ${apuesta} para apostar."
        )

    # Descontar apuesta
    user.saldo -= apuesta
    valor_casa = 0
    valor_usuario = 0

    # Generar cartas aleatorias
    filtro = random.randint(1,3)
    if filtro == 1:
        valor_usuario = random.randint(1, 7)
        valor_casa = random.randint(1, 13)
    elif filtro == 2:
        valor_usuario = random.randint(1, 10)
        valor_casa = random.randint(1, 13)
    else:
        valor_usuario = random.randint(1, 13)
        valor_casa = random.randint(1, 13)
    
    # Elegir palos aleatorios (solo para visualización)
    palo_usuario = random.choice(PALOS)
    palo_casa = random.choice(PALOS)
    
    # Determinar resultado
    resultado = ""
    mensaje = ""
    ganancia = 0
    
    if valor_usuario > valor_casa:
        # Usuario gana
        resultado = "gana_usuario"
        ganancia = apuesta * 2
        user.saldo += ganancia
        mensaje = f"¡Ganaste! Tu carta ({VALORES_CARTAS[valor_usuario][0]}) es mayor que la de la casa ({VALORES_CARTAS[valor_casa][0]}). Has ganado ${ganancia} 🎉"
    elif valor_usuario < valor_casa:
        # Casa gana
        resultado = "gana_casa"
        mensaje = f"Perdiste. Tu carta ({VALORES_CARTAS[valor_usuario][0]}) es menor que la de la casa ({VALORES_CARTAS[valor_casa][0]}). Has perdido ${apuesta} 😢"
    else:
        # Empate
        resultado = "empate"
        # Devolver la apuesta
        user.saldo += apuesta
        mensaje = f"¡Empate! Ambos sacaron {VALORES_CARTAS[valor_usuario][0]}. Se devuelve tu apuesta de ${apuesta}."

    db.commit()
    db.refresh(user)

    return {
        "resultado": resultado,
        "carta_usuario": {
            "valor": valor_usuario,
            "nombre": VALORES_CARTAS[valor_usuario][0],
            "simbolo": VALORES_CARTAS[valor_usuario][1],
            "palo": palo_usuario
        },
        "carta_casa": {
            "valor": valor_casa,
            "nombre": VALORES_CARTAS[valor_casa][0],
            "simbolo": VALORES_CARTAS[valor_casa][1],
            "palo": palo_casa
        },
        "mensaje": mensaje,
        "ganancia": ganancia,
        "apuesta": apuesta,
        "nuevo_saldo": user.saldo
    }

# Opcional: Endpoint para obtener estadísticas de probabilidades
@router.get("/juegos/cartamayor/probabilidades")
def obtener_probabilidades():
    """
    Calcula las probabilidades teóricas del juego
    """
    total_combinaciones = 13 * 13  # 13 valores para cada jugador
    
    # Probabilidades:
    # - Usuario gana: cuando su carta es mayor
    # - Casa gana: cuando su carta es mayor
    # - Empate: cuando son iguales
    
    # Contar combinaciones
    gana_usuario = 0
    gana_casa = 0
    empates = 0
    
    for i in range(1, 14):
        for j in range(1, 14):
            if i > j:
                gana_usuario += 1
            elif i < j:
                gana_casa += 1
            else:
                empates += 1
    
    return {
        "probabilidades": {
            "gana_usuario": round(gana_usuario / total_combinaciones * 100, 2),
            "gana_casa": round(gana_casa / total_combinaciones * 100, 2),
            "empate": round(empates / total_combinaciones * 100, 2)
        },
        "combinaciones": {
            "total": total_combinaciones,
            "gana_usuario": gana_usuario,
            "gana_casa": gana_casa,
            "empate": empates
        }
    }