# app/auth.py
from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
import os
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from ..models import usuario
from ..database import get_db

# 🔹 Cargar variables de entorno
load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM", "HS256")  # Por si no está definido en .env, poner un valor por defecto
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 15))

# 🔹 Manejo de contraseñas
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 🔹 Esquema OAuth2
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

# -------------------------------
# Funciones de autenticación
# -------------------------------

def hash_password(password: str) -> str:
    """Hashea una contraseña usando bcrypt."""
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica que la contraseña ingresada coincida con el hash."""
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: timedelta = None) -> str:
    """Genera un token JWT con fecha de expiración."""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> usuario.Usuario:
    """Obtiene el usuario actual a partir del token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudo validar las credenciales",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(usuario.Usuario).filter(usuario.Usuario.id == int(user_id)).first()
    if user is None:
        raise credentials_exception

    return user

def verificar_admin(current_user: usuario.Usuario = Depends(get_current_user)):
    """Dependencia para verificar permisos de administrador"""
    if current_user.username != "admin":
        raise HTTPException(status_code=403, detail="No autorizado - Se requieren permisos de administrador")
    return current_user