from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
import random
from ...models.usuario import Usuario
from ...database import get_db
from ...api.auth import get_current_user

router = APIRouter()

# Configuración del juego
APUESTAS_PERMITIDAS = [100, 500, 1000, 2000, 5000]
MULTIPLICADORES = {
    "doble_6": 10,
    "doble_otro": 5
}

@router.get("/juego/dados/apuestas-permitidas")
def obtener_configuracion():
    """
    Devuelve las apuestas permitidas y los multiplicadores
    para que el frontend configure la UI.
    """
    return {
        "apuestas_permitidas": APUESTAS_PERMITIDAS,
        "multiplicadores": MULTIPLICADORES
    }

@router.post("/juego/dados")
def lanzar_dados(
    apuesta: int = Query(..., description="Cantidad apostada"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    # Validar apuesta
    if apuesta not in APUESTAS_PERMITIDAS:
        raise HTTPException(status_code=400, detail="Apuesta no permitida")

    usuario = db.query(Usuario).filter(Usuario.id == current_user.id).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if usuario.saldo < apuesta:
        raise HTTPException(
            status_code=400,
            detail=f"Saldo insuficiente para jugar. Se requieren ${apuesta}"
        )

    # Descontar apuesta
    usuario.saldo -= apuesta

    # Lanzar los dados
    dado1 = random.randint(1, 6)
    dado2 = random.randint(1, 6)

    ganancia = 0
    mensaje = "Has perdido. Sigue intentando."
    tipo_resultado = "sin_premio"

    # Lógica de premios
    if dado1 == 6 and dado2 == 6:
        ganancia = apuesta * MULTIPLICADORES["doble_6"]
        mensaje = f"¡Felicidades! Sacaste doble 6 y ganaste {MULTIPLICADORES['doble_6']}× tu apuesta."
        tipo_resultado = "doble_6"
    elif dado1 == dado2:
        ganancia = apuesta * MULTIPLICADORES["doble_otro"]
        mensaje = f"¡Doble {dado1}! Ganaste {MULTIPLICADORES['doble_otro']}× tu apuesta."
        tipo_resultado = "doble_otro"

    # Actualizar saldo
    usuario.saldo += ganancia
    db.commit()
    db.refresh(usuario)

    return {
        "dado1": dado1,
        "dado2": dado2,
        "ganancia": ganancia,
        "nuevo_saldo": usuario.saldo,
        "mensaje": mensaje,
        "tipo_resultado": tipo_resultado
    }
