import os
from random import choice
from typing import List
from fastapi import APIRouter, FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session
from ...database import get_db
from ...api.auth import get_current_user
from ...models.usuario import Usuario

router = APIRouter()

# Configuración de juegos
COSTO_RULETA = 500
OPCIONES_RULETA = [
    ("Mega Premio", 10, "Mega Premio"),
    ("Gran Premio", 5, "Gran premio"),
    ("Gran Premio", 5, "Gran premio"),
    ("Premio Doble", 2, "Ganaste el doble"),
    ("Premio Doble", 2, "Ganaste el doble"),
    ("Premio Doble", 2, "Ganaste el doble"),
    ("Premio Doble", 2, "Ganaste el doble"),
    ("Free", 0, "Giro gratis"),
    ("Sin Premio", 0, "Nada..."),
    ("Sin Premio", 0, "Nada..."),
    ("Sin Premio", 0, "Nada..."),
    ("Sin Premio", 0, "Nada..."),
    ("Sin Premio", 0, "Nada..."),
    ("Sin Premio", 0, "Nada..."),
    ("Sin Premio", 0, "Nada..."),
    ("Sin Premio", 0, "Nada..."),
    ("Sin Premio", 0, "Nada..."),
    ("Sin Premio", 0, "Nada..."),
    ("Sin Premio", 0, "Nada..."),
    ("Sin Premio", 0, "Nada..."),
    ("Sin Premio", 0, "Nada..."),
    ("Sin Premio", 0, "Nada..."),
    ("Sin Premio", 0, "Nada..."),
    ("Sin Premio", 0, "Nada..."),
    ("Sin Premio", 0, "Nada..."),
    ("Sin Premio", 0, "Nada..."),
    ("Sin Premio", 0, "Nada..."),
    ("Sin Premio", 0, "Nada..."),
    ("Sin Premio", 0, "Nada..."),
    ("Sin Premio", 0, "Nada..."),
    ("Sin Premio", 0, "Nada..."),
    ("Sin Premio", 0, "Nada..."),
    ("Sin Premio", 0, "Nada..."),
    ("Sin Premio", 0, "Nada..."),
    ("Sin Premio", 0, "Nada..."),
    ("Sin Premio", 0, "Nada..."),
    ("Sin Premio", 0, "Nada..."),
    ("Sin Premio", 0, "Nada..."),
    ("Sin Premio", 0, "Nada...")
]

@router.post("/juegos/ruleta")
def jugar_ruleta(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    # Recargar el usuario en la sesión actual
    user = db.query(Usuario).filter(Usuario.id == current_user.id).first()

    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if user.saldo < COSTO_RULETA:
        raise HTTPException(
            status_code=400, 
            detail=f"Saldo insuficiente. Necesitas ${COSTO_RULETA} para jugar."
        )

    # Elegir resultado
    nombre, multiplicador, mensaje = choice(OPCIONES_RULETA)

    # Descontar costo (excepto giro gratis)
    if nombre != "Free":
        user.saldo -= COSTO_RULETA
    ganancia = 0
    if multiplicador > 0:
        ganancia = COSTO_RULETA * multiplicador
        user.saldo += ganancia

    db.commit()
    db.refresh(user)

    return {
        "resultado": nombre,
        "mensaje": mensaje,
        "ganancia": ganancia,
        "costo_juego": COSTO_RULETA,
        "nuevo_saldo": user.saldo
    }