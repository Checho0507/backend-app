from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import List
import random
from ..models import usuario, resultado_sorteo
from ..database import get_db
from ..api.auth import get_current_user
from ..crud import autenticar_usuario, hash_password
from ..schemas.usuario import UsuarioCreate, UsuarioOut
from ..schemas.auth import Token, UsuarioLogin


router = APIRouter()

# ========================
# ENDPOINTS DE AUTENTICACIÓN
# ========================
@router.post("/register", response_model=UsuarioOut)
def registrar_usuario(user: UsuarioCreate, db: Session = Depends(get_db)):
    """Registrar nuevo usuario en la plataforma"""
    # Verificar si el email ya existe
    if db.query(usuario.Usuario).filter(usuario.Usuario.email == user.email).first():
        raise HTTPException(status_code=400, detail="El correo ya está en uso")

    # Verificar si el username ya existe
    if db.query(usuario.Usuario).filter(usuario.Usuario.username == user.username).first():
        raise HTTPException(status_code=400, detail="El nombre de usuario ya está en uso")
    
    # Convertir referido_por a int o usar 0 si es None
    if user.referido_por is None:
        ref_id = 0
    else:
        ref_id = int(user.referido_por)

    # Crear nuevo usuario
    nuevo_usuario = usuario.Usuario(
        id=random.randint(10000000, 99999999),
        username=user.username,
        email=user.email,
        password_hash=hash_password(user.password),
        referido_por=ref_id,
        saldo=1000 if ref_id != 0 else 0  # Bonus por referido
    )

    db.add(nuevo_usuario)
    db.commit()
    db.refresh(nuevo_usuario)

    # Dar bonus al referidor si existe
    if ref_id != 0:
        referidor = db.query(usuario.Usuario).filter_by(id=ref_id).first()
        if referidor:
            referidor.saldo += 100
            db.commit()

    return nuevo_usuario

@router.post("/login", response_model=Token)
def iniciar_sesion(data: UsuarioLogin, db: Session = Depends(get_db)):
    """Iniciar sesión y obtener token JWT"""
    return autenticar_usuario(db, data.username, data.password)

@router.get("/me", response_model=UsuarioOut)
def obtener_info_usuario_actual(
    db: Session = Depends(get_db),
    current_user: usuario.Usuario = Depends(get_current_user)
):
    """Obtener información del usuario logueado"""
    return current_user

@router.get("/usuario/info")
def obtener_info_basica_usuario(current_user: usuario.Usuario = Depends(get_current_user)):
    """Obtener información básica del usuario (ID, username, saldo)"""
    return {
        "id": current_user.id,
        "username": current_user.username,
        "saldo": current_user.saldo
    }