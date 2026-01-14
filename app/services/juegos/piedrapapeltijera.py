from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import random
from ...database import get_db
from ...api.auth import get_current_user
from ...models.usuario import Usuario

router = APIRouter()

APUESTA_MINIMA = 100

# Diccionario de opciones
OPCIONES = {
    "piedra": {
        "nombre": "Piedra",
        "emoji": "✊",
        "vence_a": ["tijera"],
        "es_vencido_por": ["papel"]
    },
    "papel": {
        "nombre": "Papel",
        "emoji": "🖐",
        "vence_a": ["piedra"],
        "es_vencido_por": ["tijera"]
    },
    "tijera": {
        "nombre": "Tijera",
        "emoji": "✌️",
        "vence_a": ["papel"],
        "es_vencido_por": ["piedra"]
    }
}

@router.post("/juegos/piedrapapeltijera")
def jugar_piedra_papel_tijera(
    apuesta: int,
    eleccion: str,  # "piedra", "papel" o "tijera"
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    """
    Juego de Piedra, Papel o Tijera.
    El usuario apuesta y elige una opción.
    La máquina elige aleatoriamente.
    """
    
    # Recargar el usuario en la sesión actual
    user = db.query(Usuario).filter(Usuario.id == current_user.id).first()

    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    # Validar elección
    if eleccion.lower() not in OPCIONES:
        raise HTTPException(status_code=400, detail="Elección no válida. Debe ser 'piedra', 'papel' o 'tijera'")

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

    # Máquina elige aleatoriamente
    eleccion_maquina = random.choice(list(OPCIONES.keys()))
    
    # Determinar resultado
    resultado = ""
    mensaje = ""
    ganancia = 0
    
    if eleccion == eleccion_maquina:
        # Empate
        resultado = "empate"
        user.saldo += apuesta  # Devolver apuesta
        mensaje = f"¡Empate! Ambos eligieron {OPCIONES[eleccion]['nombre']} {OPCIONES[eleccion]['emoji']}. Se devuelve tu apuesta de ${apuesta}."
    elif eleccion_maquina in OPCIONES[eleccion]["vence_a"]:
        # Usuario gana
        resultado = "gana_usuario"
        ganancia = apuesta * 2
        user.saldo += ganancia
        mensaje = f"¡Ganaste! {OPCIONES[eleccion]['nombre']} {OPCIONES[eleccion]['emoji']} vence a {OPCIONES[eleccion_maquina]['nombre']} {OPCIONES[eleccion_maquina]['emoji']}. Has ganado ${ganancia} 🎉"
    else:
        # Máquina gana
        resultado = "gana_maquina"
        mensaje = f"Perdiste. {OPCIONES[eleccion_maquina]['nombre']} {OPCIONES[eleccion_maquina]['emoji']} vence a {OPCIONES[eleccion]['nombre']} {OPCIONES[eleccion]['emoji']}. Has perdido ${apuesta} 😢"

    db.commit()
    db.refresh(user)

    return {
        "resultado": resultado,
        "eleccion_usuario": {
            "tipo": eleccion,
            "nombre": OPCIONES[eleccion]["nombre"],
            "emoji": OPCIONES[eleccion]["emoji"]
        },
        "eleccion_maquina": {
            "tipo": eleccion_maquina,
            "nombre": OPCIONES[eleccion_maquina]["nombre"],
            "emoji": OPCIONES[eleccion_maquina]["emoji"]
        },
        "mensaje": mensaje,
        "ganancia": ganancia,
        "apuesta": apuesta,
        "nuevo_saldo": user.saldo
    }

@router.get("/juegos/piedrapapeltijera/probabilidades")
def obtener_probabilidades():
    """
    Calcula las probabilidades teóricas del juego
    """
    total_opciones = 3
    total_combinaciones = total_opciones * total_opciones
    
    # Cada jugador tiene 3 opciones posibles
    # Empates: 3 (cuando ambos eligen lo mismo)
    # Usuario gana: cuando la elección del usuario vence a la de la máquina
    # Máquina gana: cuando la elección de la máquina vence a la del usuario
    
    # Contar combinaciones
    gana_usuario = 0
    gana_maquina = 0
    empates = 0
    
    for usuario_opcion in OPCIONES:
        for maquina_opcion in OPCIONES:
            if usuario_opcion == maquina_opcion:
                empates += 1
            elif maquina_opcion in OPCIONES[usuario_opcion]["vence_a"]:
                gana_usuario += 1
            else:
                gana_maquina += 1
    
    return {
        "probabilidades": {
            "gana_usuario": round(gana_usuario / total_combinaciones * 100, 2),
            "gana_maquina": round(gana_maquina / total_combinaciones * 100, 2),
            "empate": round(empates / total_combinaciones * 100, 2)
        },
        "combinaciones": {
            "total": total_combinaciones,
            "gana_usuario": gana_usuario,
            "gana_maquina": gana_maquina,
            "empate": empates
        },
        "reglas": {
            "piedra": f"{OPCIONES['piedra']['emoji']} Piedra vence a {OPCIONES['tijera']['emoji']} Tijera",
            "papel": f"{OPCIONES['papel']['emoji']} Papel vence a {OPCIONES['piedra']['emoji']} Piedra",
            "tijera": f"{OPCIONES['tijera']['emoji']} Tijera vence a {OPCIONES['papel']['emoji']} Papel"
        }
    }