from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from sqlalchemy.orm import Session
from typing import List
from ..models import usuario
from ..database import get_db
from ..api.auth import get_current_user, verificar_admin
from ..schemas.verificacion import VerificacionOut
from ..crud import crear_solicitud_verificacion, listar_verificaciones_pendientes

router = APIRouter()


# ========================
# SISTEMA DE VERIFICACIÓN
# ========================
@router.post("/verificate")
def solicitar_verificacion(
    archivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: usuario.Usuario = Depends(get_current_user)
):
    current_user.verificacion_pendiente = True
    """Subir documentos para verificación de cuenta"""
    if current_user.verificado:
        raise HTTPException(status_code=400, detail="Tu cuenta ya está verificada.")

    return crear_solicitud_verificacion(db, current_user.id, archivo)

@router.get("/verificaciones/pendientes", response_model=List[VerificacionOut])
def obtener_verificaciones_pendientes(
    db: Session = Depends(get_db),
    current_user: usuario.Usuario = Depends(verificar_admin)
):
    """Obtener lista de verificaciones pendientes (admin)"""
    return listar_verificaciones_pendientes(db)
