from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import random
from ...database import get_db
from ...api.auth import get_current_user
from ...models.usuario import Usuario

router = APIRouter()

APUESTA_MINIMA = 50

@router.post("/juegos/caraosello")
def jugar_cara_sello(
    apuesta: int,
    eleccion: str,  # "cara" o "sello"
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    """
    Juego de Cara o Sello.
    El usuario apuesta a cara o sello.
    Si acierta, gana el doble (apuesta * 2).
    Si falla, pierde la apuesta.
    """
    
    # Recargar el usuario en la sesión actual
    user = db.query(Usuario).filter(Usuario.id == current_user.id).first()

    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    # Validar elección
    if eleccion.lower() not in ["cara", "sello"]:
        raise HTTPException(status_code=400, detail="Elección no válida. Debe ser 'cara' o 'sello'")

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

    # Generar resultado aleatorio (50/50)
    resultado = random.choice(["cara", "sello", "perdiste"])  # Added "perdiste" to ensure fair distribution
    
    # Determinar si ganó
    gano = eleccion.lower() == resultado
    if resultado == "perdiste":
        gano = False
        if eleccion.lower() == "cara":
            resultado = "sello"
        else:
            resultado = "cara"
    ganancia = 0
    
    if gano:
        # Gana el doble de lo apostado
        ganancia = apuesta * 2
        user.saldo += ganancia
        mensaje = f"¡Ganaste! Salió {resultado.upper()}. Has ganado ${ganancia} 🎉"
    else:
        mensaje = f"Perdiste. Salió {resultado.upper()}. Has perdido ${apuesta} 😢"

    db.commit()
    db.refresh(user)

    return {
        "resultado": resultado,
        "gano": gano,
        "mensaje": mensaje,
        "ganancia": ganancia,
        "apuesta": apuesta,
        "nuevo_saldo": user.saldo
    }