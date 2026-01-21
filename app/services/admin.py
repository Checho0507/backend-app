from datetime import datetime
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from ..database import get_db
from ..api.auth import verificar_admin
from ..models.usuario import Usuario
from ..schemas.usuario import UsuarioOut
from ..models.verificacion import Verificacion
from ..schemas.verificacion import VerificacionOut
from ..services.mail import smtp2go
from fastapi import BackgroundTasks
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

@router.post("/admin/verificar/{user_id}")
async def admin_verificar_usuario(
    user_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(verificar_admin)  # Asumiendo que tienes esta función
):
    """Verificar usuario manualmente - Versión simple"""
    
    # Buscar usuario
    usuario = db.query(Usuario).filter(Usuario.id == user_id).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    if usuario.verificado:
        raise HTTPException(status_code=400, detail="Usuario ya verificado")
    
    if not usuario.email:
        raise HTTPException(status_code=400, detail="Usuario sin email")
     # Dar bonus al referidor si existe
    if usuario.referido_por != 0:
        referidor = db.query(Usuario).filter_by(id=usuario.referido_por).first()
        if referidor:
            referidor.saldo += 2000
        if referidor.referido_por != 0:
            sub_referidor = db.query(Usuario).filter_by(id=referidor.referido_por).first()
            if sub_referidor: 
                sub_referidor.saldo += 100
            db.commit()
    #DAR BONUS PORSUBREFERIDO
    
    # Marcar como verificado
    usuario.verificado = True
    usuario.fecha_verificacion = datetime.now()
    usuario.verificacion_pendiente = False
    usuario.saldo += 10000  # Bonus por verificación
    db.commit()
    
    # Función para enviar email en background
    def enviar_email():
        try:
            resultado = smtp2go.enviar_verificacion(usuario)
            # Opcional: marcar que se envió el correo
            if resultado.get("success"):
                usuario.correo_enviado = True
                usuario.correo_fecha = datetime.now()
                db.commit()
        except Exception as e:
            print(f"Error enviando email: {e}")
    
    # Agregar tarea en background
    background_tasks.add_task(enviar_email)
    
    return {
        "ok": True,
        "mensaje": f"Usuario {usuario.username} verificado",
        "email": usuario.email,
        "verificado": True,
        "saldo": usuario.saldo
    }

# Endpoint para verificar estado de envío de correo
@router.get("/admin/verificar/{user_id}/status")
def verificar_estado_correo(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(verificar_admin)
):
    """Verifica si el correo de verificación fue enviado"""
    usuario = db.query(Usuario).filter(Usuario.id == user_id).first()
    
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    return {
        "usuario_id": usuario.id,
        "usuario": usuario.username,
        "email": usuario.email,
        "verificado": usuario.verificado,
        "correo_verificacion_enviado": usuario.correo_verificacion_enviado,
        "correo_verificacion_fecha": usuario.correo_verificacion_fecha,
        "fecha_verificacion": usuario.fecha_verificacion
    }


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
    
