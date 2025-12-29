# app/services/transacciones.py (VERSIÓN CORREGIDA)

from fastapi import APIRouter, Body, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import Optional, List
import uuid
from datetime import datetime
import os

from ..database import SessionLocal
from ..models import usuario as usuario_model
from ..models import deposito as deposito_model
from ..models import retiro as retiro_model
from ..services.auth import get_current_user

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ========================
# ENDPOINTS DE ADMINISTRACIÓN PARA DEPÓSITOS
# ========================

@router.get("/admin/depositos/pendientes")
async def obtener_depositos_pendientes(
    current_user: usuario_model.Usuario = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Obtener depósitos pendientes (solo admin)"""
    if current_user.username != "admin":
        raise HTTPException(status_code=403, detail="Acceso denegado. Solo administradores")

    try:
        # ✅ Usar nombres de variable diferentes
        depositos_pendientes = db.query(deposito_model.Deposito).filter(
            deposito_model.Deposito.estado == "PENDIENTE"
        ).order_by(deposito_model.Deposito.fecha_solicitud.desc()).all()

        # Enriquecer con información del usuario
        resultados = []
        for dep in depositos_pendientes:  # ✅ Usar 'dep' en lugar de 'deposito'
            usr = db.query(usuario_model.Usuario).filter(
                usuario_model.Usuario.id == dep.usuario_id
            ).first()
            
            resultados.append({
                "id": dep.id,
                "usuario_id": dep.usuario_id,
                "monto": float(dep.monto),  # ✅ Convertir a float para JSON
                "metodo_pago": dep.metodo_pago,
                "referencia": dep.referencia,
                "estado": dep.estado,
                "comprobante_url": dep.comprobante_url,
                "fecha_solicitud": dep.fecha_solicitud.isoformat() if dep.fecha_solicitud else None,
                "fecha_procesamiento": dep.fecha_procesamiento.isoformat() if dep.fecha_procesamiento else None,
                "usuario": {
                    "username": usr.username if usr else "Desconocido",
                    "email": usr.email if usr else None,
                    "verificado": usr.verificado if usr else False
                } if usr else None
            })
        
        return resultados
    
    except Exception as e:
        print(f"❌ Error en obtener_depositos_pendientes: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error al obtener depósitos: {str(e)}"
        )

@router.post("/admin/depositos/{deposito_id}/aprobar")
async def aprobar_deposito(
    deposito_id: int,
    current_user: usuario_model.Usuario = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Aprobar un depósito pendiente (solo admin)"""
    if current_user.username != "admin":
        raise HTTPException(status_code=403, detail="Acceso denegado. Solo administradores")

    try:
        # Buscar el depósito usando un nombre de variable único
        deposito_obj = db.query(deposito_model.Deposito).filter(
            deposito_model.Deposito.id == deposito_id
        ).first()
        
        if not deposito_obj:
            raise HTTPException(status_code=404, detail="Depósito no encontrado")
        
        if deposito_obj.estado != "PENDIENTE":
            raise HTTPException(status_code=400, detail="El depósito ya fue procesado")

        # Buscar usuario asociado al depósito
        usuario_deposito = db.query(usuario_model.Usuario).filter(
            usuario_model.Usuario.id == deposito_obj.usuario_id
        ).first()
        
        if not usuario_deposito:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        
        print(f"[APROBAR DEPÓSITO] Usuario: {usuario_deposito.username}, Saldo actual: {usuario_deposito.saldo}, Monto a sumar: {deposito_obj.monto}")
        
        # Actualizar saldo del usuario
        usuario_deposito.saldo = float(usuario_deposito.saldo) + float(deposito_obj.monto)
        
        # Actualizar estado del depósito
        deposito_obj.estado = "APROBADO"
        deposito_obj.fecha_procesamiento = datetime.now()
        
        # Guardar cambios
        db.commit()
        
        # Refrescar los objetos para obtener los valores actualizados
        db.refresh(usuario_deposito)
        db.refresh(deposito_obj)
        
        print(f"[APROBAR DEPÓSITO] Nuevo saldo: {usuario_deposito.saldo}")
        
        return {
            "mensaje": "Depósito aprobado correctamente",
            "deposito_id": deposito_obj.id,
            "usuario_id": usuario_deposito.id,
            "monto": float(deposito_obj.monto),
            "nuevo_saldo_usuario": float(usuario_deposito.saldo),
            "estado_deposito": deposito_obj.estado
        }
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"❌ Error al aprobar depósito: {e}")
        raise HTTPException(status_code=500, detail=f"Error al aprobar: {str(e)}")

@router.post("/admin/depositos/{deposito_id}/rechazar")
async def rechazar_deposito(
    deposito_id: int,
    current_user: usuario_model.Usuario = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Rechazar un depósito pendiente (solo admin)"""
    if current_user.username != "admin":
        raise HTTPException(status_code=403, detail="Acceso denegado. Solo administradores")

    try:
        dep = db.query(deposito_model.Deposito).filter(
            deposito_model.Deposito.id == deposito_id
        ).first()
        
        if not dep:
            raise HTTPException(status_code=404, detail="Depósito no encontrado")
        
        if dep.estado != "PENDIENTE":
            raise HTTPException(status_code=400, detail="El depósito ya fue procesado")
        
        # Actualizar estado del depósito
        dep.estado = "RECHAZADO"
        dep.fecha_procesamiento = datetime.now()
        
        db.commit()
        
        return {
            "mensaje": "Depósito rechazado correctamente",
            "deposito_id": dep.id
        }
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"❌ Error al rechazar depósito: {e}")
        raise HTTPException(status_code=500, detail=f"Error al rechazar: {str(e)}")

@router.post("/deposito")
async def realizar_deposito(
    monto: float = Form(...),
    metodo_pago: str = Form(...),
    comprobante: Optional[UploadFile] = File(None),
    current_user: usuario_model.Usuario = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Realizar un nuevo depósito"""
    print(f"[DEPOSITO] Usuario: {current_user.username if current_user else 'None'}")
    
    if not current_user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    # Validaciones
    if monto < 10000:
        raise HTTPException(status_code=400, detail="Monto mínimo: $10,000 COP")
    
    if monto > 5000000:
        raise HTTPException(status_code=400, detail="Monto máximo: $5,000,000 COP")
    
    if not current_user.verificado and not comprobante:
        raise HTTPException(status_code=400, detail="Comprobante requerido para usuarios no verificados")
    
    # Procesar comprobante
    comprobante_url = None
    if comprobante:
        try:
            os.makedirs("recibos", exist_ok=True)
            filename = f"{current_user.id}_{int(datetime.now().timestamp())}_{comprobante.filename}"
            file_location = f"recibos/{filename}"
            
            with open(file_location, "wb+") as file_object:
                content = await comprobante.read()
                file_object.write(content)
            
            comprobante_url = f"recibos/{filename}"
            print(f"✅ Comprobante guardado en: {comprobante_url}")
        except Exception as e:
            print(f"❌ Error al guardar comprobante: {e}")
            raise HTTPException(status_code=500, detail="Error al guardar el comprobante")
    
    # Generar referencia
    referencia = f"DEP{str(uuid.uuid4())[:8].upper()}"
    
    try:
        # Crear depósito
        nuevo_deposito = deposito_model.Deposito(
            usuario_id=current_user.id,
            monto=monto,
            metodo_pago=metodo_pago,
            referencia=referencia,
            estado="PENDIENTE",
            comprobante_url=comprobante_url,
            fecha_solicitud=datetime.now(),
            fecha_procesamiento=datetime.now()
        )
        
        db.add(nuevo_deposito)
        db.commit()
        db.refresh(nuevo_deposito)
        
        print(f"✅ Depósito creado: {referencia} para usuario {current_user.username}")
        
        return {
            "mensaje": "Depósito solicitado correctamente",
            "referencia": referencia,
            "nuevo_saldo": float(current_user.saldo),
            "estado": "PENDIENTE",
            "detalles": {
                "monto": float(monto),
                "metodo_pago": metodo_pago,
                "fecha": nuevo_deposito.fecha_solicitud.isoformat()
            }
        }
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error al crear depósito: {e}")
        raise HTTPException(status_code=500, detail="Error al procesar el depósito")

# ========================
# ENDPOINTS PARA HISTORIAL DE DEPÓSITOS
# ========================

@router.get("/mis-depositos")
async def obtener_mis_depositos(
    current_user: usuario_model.Usuario = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Obtener el historial de depósitos del usuario actual"""
    try:
        depositos = db.query(deposito_model.Deposito).filter(
            deposito_model.Deposito.usuario_id == current_user.id
        ).order_by(deposito_model.Deposito.fecha_solicitud.desc()).all()

        resultados = []
        for dep in depositos:
            resultados.append({
                "id": dep.id,
                "monto": float(dep.monto),
                "metodo_pago": dep.metodo_pago,
                "referencia": dep.referencia,
                "estado": dep.estado,
                "comprobante_url": dep.comprobante_url,
                "fecha_solicitud": dep.fecha_solicitud.isoformat() if dep.fecha_solicitud else None,
                "fecha_procesamiento": dep.fecha_procesamiento.isoformat() if dep.fecha_procesamiento else None,
            })

        return resultados

    except Exception as e:
        print(f"❌ Error en obtener_mis_depositos: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error al obtener depósitos: {str(e)}"
        )

@router.get("/deposito/{deposito_id}")
async def obtener_detalle_deposito(
    deposito_id: int,
    current_user: usuario_model.Usuario = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Obtener detalle de un depósito específico"""
    try:
        deposito = db.query(deposito_model.Deposito).filter(
            deposito_model.Deposito.id == deposito_id
        ).first()

        if not deposito:
            raise HTTPException(status_code=404, detail="Depósito no encontrado")

        # Verificar que el usuario sea el propietario o admin
        if deposito.usuario_id != current_user.id and current_user.username != "admin":
            raise HTTPException(status_code=403, detail="No autorizado")

        return {
            "id": deposito.id,
            "usuario_id": deposito.usuario_id,
            "monto": float(deposito.monto),
            "metodo_pago": deposito.metodo_pago,
            "referencia": deposito.referencia,
            "estado": deposito.estado,
            "comprobante_url": deposito.comprobante_url,
            "fecha_solicitud": deposito.fecha_solicitud.isoformat() if deposito.fecha_solicitud else None,
            "fecha_procesamiento": deposito.fecha_procesamiento.isoformat() if deposito.fecha_procesamiento else None
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error en obtener_detalle_deposito: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error al obtener depósito: {str(e)}"
        )
        
# ========================
# ENDPOINTS PARA RETIROS
# ========================

@router.post("/transacciones/retiro")
async def realizar_retiro(
    monto: float = Body(...),
    metodo_retiro: str = Body(...),
    cuenta_destino: str = Body(...),
    comision: Optional[float] = Body(...),
    total: Optional[float] = Body(...),
    current_user: usuario_model.Usuario = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Realizar una solicitud de retiro"""
    print(f"[RETIRO] Usuario: {current_user.username}")
    
    if not current_user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    # Validaciones
    monto_minimo = 50000
    monto_maximo = 5000000 if current_user.verificado else 1000000
    
    if monto < monto_minimo:
        raise HTTPException(
            status_code=400, 
            detail=f"Monto mínimo: ${monto_minimo:,} COP"
        )
    
    if monto > monto_maximo:
        raise HTTPException(
            status_code=400, 
            detail=f"Monto máximo: ${monto_maximo:,} COP"
        )
    
    if monto > current_user.saldo:
        raise HTTPException(
            status_code=400, 
            detail=f"Saldo insuficiente. Disponible: ${current_user.saldo:,} COP"
        )
    
    if len(cuenta_destino.strip()) < 8:
        raise HTTPException(
            status_code=400, 
            detail="La cuenta destino debe tener al menos 8 caracteres"
        )
    
    try:
        # Generar referencia
        referencia = f"RET{str(uuid.uuid4())[:8].upper()}"
        
        # Crear retiro
        nuevo_retiro = retiro_model.Retiro(
            usuario_id=current_user.id,
            monto=monto,
            metodo_retiro=metodo_retiro,
            cuenta_destino=cuenta_destino.strip(),
            comision=comision if comision else 0.0,
            total=total if total else monto,
            referencia=referencia,
            estado="PENDIENTE",
            fecha_solicitud=datetime.now()
        )
        
        db.add(nuevo_retiro)
        db.commit()
        db.refresh(nuevo_retiro)
        
        print(f"✅ Retiro creado: {referencia} para usuario {current_user.username}")
        
        return {
            "mensaje": "Retiro solicitado correctamente",
            "referencia": referencia,
            "nuevo_saldo": float(current_user.saldo),
            "estado": "PENDIENTE",
            "detalles": {
                "monto": float(monto),
                "metodo_retiro": metodo_retiro,
                "fecha": nuevo_retiro.fecha_solicitud.isoformat()
            }
        }
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error al crear retiro: {e}")
        raise HTTPException(status_code=500, detail="Error al procesar el retiro")

@router.get("/mis-retiros")
async def obtener_mis_retiros(
    current_user: usuario_model.Usuario = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Obtener el historial de retiros del usuario actual"""
    try:
        retiros = db.query(retiro_model.Retiro).filter(
            retiro_model.Retiro.usuario_id == current_user.id
        ).order_by(retiro_model.Retiro.fecha_solicitud.desc()).all()

        resultados = []
        for ret in retiros:
            resultados.append({
                "id": ret.id,
                "monto": float(ret.monto),
                "metodo_retiro": ret.metodo_retiro,
                "cuenta_destino": ret.cuenta_destino,
                "referencia": ret.referencia,
                "estado": ret.estado,
                "fecha_solicitud": ret.fecha_solicitud.isoformat() if ret.fecha_solicitud else None,
                "fecha_procesamiento": ret.fecha_procesamiento.isoformat() if ret.fecha_procesamiento else None,
            })

        return resultados

    except Exception as e:
        print(f"❌ Error en obtener_mis_retiros: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error al obtener retiros: {str(e)}"
        )

# ========================
# ENDPOINTS DE ADMINISTRACIÓN PARA RETIROS
# ========================

@router.get("/admin/retiros/pendientes")
async def obtener_retiros_pendientes(
    current_user: usuario_model.Usuario = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Obtener retiros pendientes (solo admin)"""
    if current_user.username != "admin":
        raise HTTPException(status_code=403, detail="Acceso denegado. Solo administradores")

    try:
        retiros_pendientes = db.query(retiro_model.Retiro).filter(
            retiro_model.Retiro.estado == "PENDIENTE"
        ).order_by(retiro_model.Retiro.fecha_solicitud.desc()).all()

        resultados = []
        for ret in retiros_pendientes:
            usr = db.query(usuario_model.Usuario).filter(
                usuario_model.Usuario.id == ret.usuario_id
            ).first()
            
            resultados.append({
                "id": ret.id,
                "usuario_id": ret.usuario_id,
                "monto": float(ret.monto),
                "metodo_retiro": ret.metodo_retiro,
                "cuenta_destino": ret.cuenta_destino,
                "referencia": ret.referencia,
                "estado": ret.estado,
                "fecha_solicitud": ret.fecha_solicitud.isoformat() if ret.fecha_solicitud else None,
                "usuario": {
                    "username": usr.username if usr else "Desconocido",
                    "email": usr.email if usr else None,
                    "verificado": usr.verificado if usr else False
                } if usr else None
            })
        
        return resultados
    
    except Exception as e:
        print(f"❌ Error en obtener_retiros_pendientes: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error al obtener retiros: {str(e)}"
        )

@router.post("/admin/retiros/{retiro_id}/aprobar")
async def aprobar_retiro(
    retiro_id: int,
    current_user: usuario_model.Usuario = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Aprobar un retiro pendiente (solo admin)"""
    if current_user.username != "admin":
        raise HTTPException(status_code=403, detail="Acceso denegado. Solo administradores")

    try:
        retiro_obj = db.query(retiro_model.Retiro).filter(
            retiro_model.Retiro.id == retiro_id
        ).first()
        
        if not retiro_obj:
            raise HTTPException(status_code=404, detail="Retiro no encontrado")
        
        if retiro_obj.estado != "PENDIENTE":
            raise HTTPException(status_code=400, detail="El retiro ya fue procesado")

        # Buscar usuario asociado al retiro
        usuario_retiro = db.query(usuario_model.Usuario).filter(
            usuario_model.Usuario.id == retiro_obj.usuario_id
        ).first()
        
        if not usuario_retiro:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        
        # Verificar que aún tenga saldo suficiente
        if retiro_obj.monto > usuario_retiro.saldo:
            retiro_obj.estado = "RECHAZADO"
            retiro_obj.fecha_procesamiento = datetime.now()
            retiro_obj.observaciones = "Saldo insuficiente al momento de procesar"
            db.commit()
            
            return {
                "mensaje": "Retiro rechazado por saldo insuficiente",
                "retiro_id": retiro_obj.id,
                "estado": "RECHAZADO"
            }
        
        # Actualizar saldo del usuario
        usuario_retiro.saldo = float(usuario_retiro.saldo) - float(retiro_obj.monto)
        
        # Actualizar estado del retiro
        retiro_obj.estado = "APROBADO"
        retiro_obj.fecha_procesamiento = datetime.now()
        
        # Guardar cambios
        db.commit()
        
        return {
            "mensaje": "Retiro aprobado correctamente",
            "retiro_id": retiro_obj.id,
            "usuario_id": usuario_retiro.id,
            "monto": float(retiro_obj.monto),
            "nuevo_saldo_usuario": float(usuario_retiro.saldo),
            "estado_retiro": retiro_obj.estado
        }
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"❌ Error al aprobar retiro: {e}")
        raise HTTPException(status_code=500, detail=f"Error al aprobar: {str(e)}")

@router.post("/admin/retiros/{retiro_id}/rechazar")
async def rechazar_retiro(
    retiro_id: int,
    current_user: usuario_model.Usuario = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Rechazar un retiro pendiente (solo admin)"""
    if current_user.username != "admin":
        raise HTTPException(status_code=403, detail="Acceso denegado. Solo administradores")

    try:
        ret = db.query(retiro_model.Retiro).filter(
            retiro_model.Retiro.id == retiro_id
        ).first()
        
        if not ret:
            raise HTTPException(status_code=404, detail="Retiro no encontrado")
        
        if ret.estado != "PENDIENTE":
            raise HTTPException(status_code=400, detail="El retiro ya fue procesado")
        
        # Actualizar estado del retiro
        ret.estado = "RECHAZADO"
        ret.fecha_procesamiento = datetime.now()
        
        db.commit()
        
        return {
            "mensaje": "Retiro rechazado correctamente",
            "retiro_id": ret.id
        }
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"❌ Error al rechazar retiro: {e}")
        raise HTTPException(status_code=500, detail=f"Error al rechazar: {str(e)}")