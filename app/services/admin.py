from typing import List
from fastapi import APIRouter, Depends, HTTPException
from ..database import get_db
from ..api.auth import verificar_admin
from ..models.usuario import Usuario
from ..schemas.usuario import UsuarioOut
from ..models.verificacion import Verificacion
from ..schemas.verificacion import VerificacionOut
from sqlalchemy.orm import Session
from ..crud import listar_usuarios, listar_verificaciones_pendientes, verificar_usuario

router = APIRouter()

# ========================
# PANEL DE ADMINISTRACIÓN
# ========================
@router.get("/admin/usuarios", response_model=List[UsuarioOut])
def admin_listar_usuarios(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(verificar_admin)
):
    """Listar todos los usuarios (admin)"""
    return listar_usuarios(db)

@router.get("/admin/verificaciones", response_model=List[VerificacionOut])
def admin_listar_verificaciones(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(verificar_admin)
):
    """Listar verificaciones pendientes (admin)"""
    return listar_verificaciones_pendientes(db)

from fastapi import HTTPException, Depends
from sqlalchemy.orm import Session
from email import enviar_correo

@router.post("/admin/verificar/{user_id}")
def admin_verificar_usuario(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(verificar_admin)
):
    """Verificar usuario manualmente (admin)"""
    try:
        usuario = verificar_usuario(db, user_id)

        # 📧 Contenido del correo
        asunto = "Cuenta verificada con éxito"
        cuerpo = f"""
Hola {usuario.username},

Tu cuenta ha sido verificada con éxito.

Tu saldo actual es {usuario.saldo} COP.

Diviértete con responsabilidad y realiza inversiones con la mejor tasa de interés del mercado.

Atentamente,
El equipo de soporte
        """

        # Enviar correo
        enviar_correo(
            destinatario=usuario.email,
            asunto=asunto,
            cuerpo=cuerpo
        )

        return {
            "mensaje": f"Usuario {usuario.username} verificado correctamente.",
            "usuario_id": user_id,
            "usuario": usuario.username
        }

    except Exception:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")


@router.post("/admin/rechazar/{user_id}")
def admin_rechazar_verificacion(
    user_id: int, 
    comentarios: dict, 
    db: Session = Depends(get_db), 
    current_user: Usuario = Depends(verificar_admin)
):
    usuario = db.query(Usuario).filter_by(id=user_id).first()
    usuario.verificacion_pendiente = False
    """Rechazar solicitud de verificación (admin)"""
    verificacion = db.query(Verificacion).filter(
        Verificacion.usuario_id == user_id,
        Verificacion.estado == "pendiente"
    ).first()

    if not verificacion:
        raise HTTPException(status_code=404, detail="Solicitud de verificación no encontrada")

    verificacion.estado = "rechazada"
    # Opcional: guardar comentarios (requiere agregar campo al modelo)
    db.commit()

    return {
        "mensaje": "Verificación rechazada",
        "usuario_id": user_id,
        "comentarios": comentarios.get("razon", "Sin comentarios")
    }

@router.delete("/admin/usuarios/{user_id}")
def admin_eliminar_usuario(
    user_id: int, 
    db: Session = Depends(get_db), 
    current_user: Usuario = Depends(verificar_admin)
):
    """Eliminar usuario del sistema (admin)"""
    usuario = db.query(usuario.Usuario).filter_by(id=user_id).first()

    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if usuario.username == "admin":
        raise HTTPException(status_code=400, detail="No se puede eliminar al administrador")

    username_eliminado = usuario.username
    db.delete(usuario)
    db.commit()

    return {
        "mensaje": f"Usuario {username_eliminado} eliminado correctamente",
        "usuario_eliminado": username_eliminado
    }
    
