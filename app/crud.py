from datetime import datetime, timedelta
import os
import shutil

from fastapi import HTTPException, UploadFile
from jose import jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from .models.usuario import Usuario
from .models.verificacion import Verificacion
from .schemas.auth import Token


# ------------------- Configuración -------------------

SECRET_KEY = os.getenv("SECRET_KEY", "clave-secreta-segura")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ------------------- Utilidades -------------------

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: timedelta = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# ------------------- Autenticación -------------------

def authenticate_user(db: Session, username_or_email: str, password: str):
    user = db.query(Usuario).filter(
        (Usuario.username == username_or_email) |
        (Usuario.email == username_or_email)
    ).first()

    if not user or not verify_password(password, user.password_hash):
        return None
    return user

def autenticar_usuario(db: Session, username_or_email: str, password: str) -> Token:
    user = authenticate_user(db, username_or_email, password)
    if not user:
        raise HTTPException(status_code=401, detail="Credenciales inválidas")

    token = create_access_token({"sub": str(user.id)}, timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))

    return Token(
        access_token=token,
        token_type="bearer",
        user_id=user.id,
        username=user.username,
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )

# ------------------- Usuario -------------------

def listar_usuarios(db: Session):
    return db.query(Usuario).all()

def get_usuario_por_id(db: Session, user_id: int):
    return db.query(Usuario).filter(Usuario.id == user_id).first()

def verificar_usuario(db: Session, user_id: int):
    usuario = db.query(Usuario).filter(Usuario.id == user_id).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if usuario.verificado:
        raise HTTPException(status_code=400, detail="El usuario ya está verificado")

    usuario2 = None
    if usuario.referido_por:
        usuario2 = db.query(Usuario).filter(Usuario.id == usuario.referido_por).first()

    usuario.verificado = True
    usuario.saldo += 10000  # Aumenta saldo

    if usuario2:
        usuario2.saldo += 2000  # Aumenta saldo del referidor

    db.commit()
    db.refresh(usuario)
    if usuario2:
        db.refresh(usuario2)
    return usuario

# ------------------- Verificaciones -------------------

def crear_solicitud_verificacion(db: Session, user_id: int, archivo: UploadFile):
    carpeta_recibos = "recibos"
    if not os.path.exists(carpeta_recibos):
        os.makedirs(carpeta_recibos)

    filename = f"{carpeta_recibos}/{user_id}_{archivo.filename}"
    with open(filename, "wb") as buffer:
        shutil.copyfileobj(archivo.file, buffer)

    verificacion = Verificacion(
        usuario_id=user_id,
        archivo_url=filename,
        estado="pendiente"
    )

    db.add(verificacion)
    db.commit()
    db.refresh(verificacion)

    return verificacion

def listar_verificaciones_pendientes(db: Session):
    return db.query(Verificacion).filter(Verificacion.estado == "pendiente").all()

def listar_verificaciones_completas(db: Session):
    return db.query(Verificacion).all()

def actualizar_estado_verificacion(db: Session, verificacion_id: int, nuevo_estado: str):
    verificacion = db.query(Verificacion).filter(Verificacion.id == verificacion_id).first()
    if not verificacion:
        raise HTTPException(status_code=404, detail="Verificación no encontrada")

    verificacion.estado = nuevo_estado
    db.commit()
    db.refresh(verificacion)
    return verificacion
