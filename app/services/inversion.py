from datetime import date, datetime, timedelta
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import and_, func
import pytz

from ..models.usuario import Usuario
from ..models.inversion import Inversion, RetiroInversion
from ..database import get_db
from ..api.auth import get_current_user

router = APIRouter()

ZONE = pytz.timezone("America/Bogota")

@router.post("/inversion/depositar")
def depositar_inversion(
    data: dict,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    """Realizar un depósito en la inversión"""
    monto = Decimal(data.get("monto", 0))
    
    # Validar monto
    if monto < 50000 or monto > 5000000:
        raise HTTPException(
            status_code=400, 
            detail="El monto debe estar entre $50,000 y $5,000,000"
        )
    
    # Verificar saldo del usuario
    usuario = db.query(Usuario).filter(Usuario.id == current_user.id).first()
    if usuario.saldo < monto:
        raise HTTPException(
            status_code=400, 
            detail="Saldo insuficiente para realizar la inversión"
        )
    
    # Calcular fechas de retiro + 19 horas
    ahora = datetime.today() + timedelta(hours=19)
    proximo_retiro_intereses = ahora + timedelta(days=30)
    proximo_retiro_capital = ahora + timedelta(days=180)
    
    # Descontar del saldo del usuario
    usuario.saldo -= monto
    
    # Crear registro de inversión
    nueva_inversion = Inversion(
        usuario_id=usuario.id,
        monto=monto,
        fecha_deposito=ahora,
        fecha_proximo_retiro_intereses=proximo_retiro_intereses,
        fecha_proximo_retiro_capital=proximo_retiro_capital,
        tasa_interes=300.0
    )
    
    db.add(nueva_inversion)
    db.commit()
    db.refresh(nueva_inversion)
    db.refresh(usuario)
    
    return {
        "success": True,
        "message": f"✅ Inversión de ${monto:,.0f} realizada con éxito",
        "nuevo_saldo": Decimal(usuario.saldo),
        "inversion_id": nueva_inversion.id,
        "proximo_retiro_intereses": proximo_retiro_intereses.isoformat(),
        "proximo_retiro_capital": proximo_retiro_capital.isoformat()
    }
    
@router.get("/inversion/estado")
def obtener_estado_inversion(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    """Obtener estado actual de las inversiones del usuario"""
    ahora = datetime.now(ZONE)  # Usar datetime.now con zona horaria
    
    # Obtener todas las inversiones activas del usuario
    inversiones = db.query(Inversion).filter(
        and_(
            Inversion.usuario_id == current_user.id,
            Inversion.activa == True
        )
    ).all()
    
    total_invertido = sum(inv.monto for inv in inversiones)
    total_intereses = 0
    total_intereses_disponibles = 0
    
    detalles_inversiones = []
    
    for inversion in inversiones:
        # Fecha base para cálculo
        fecha_base = inversion.fecha_ultimo_retiro_intereses or inversion.fecha_deposito
        
        # Calcular segundos transcurridos usando total_seconds()
        segundos_transcurridos = (ahora - fecha_base).total_seconds()
        
        # Asegurarse de que los segundos no sean negativos
        if segundos_transcurridos < 0:
            segundos_transcurridos = 0
        
        # Calcular interés por segundo (tasa anual 300%)
        # 300% = 3.0 en decimal, dividido entre 365 días y 86400 segundos
        tasa_segundo = Decimal(inversion.tasa_interes) / Decimal(100) / Decimal(365) / Decimal(86400)
        interes_por_segundo = Decimal(inversion.monto) * tasa_segundo 
        
        # Interés acumulado desde el inicio o último retiro
        interes_acumulado_desde_retiro = interes_por_segundo * Decimal(segundos_transcurridos)
        
        # Interés total acumulado (sumando lo que ya estaba acumulado)
        interes_total = Decimal(inversion.interes_acumulado or 0) + interes_acumulado_desde_retiro
        
        # Verificar si puede retirar intereses
        puede_retirar_intereses = ahora >= inversion.fecha_proximo_retiro_intereses
        puede_retirar_capital = ahora >= inversion.fecha_proximo_retiro_capital
        
        if puede_retirar_intereses:
            total_intereses_disponibles += interes_total
        
        total_intereses += interes_total
        
        detalles_inversiones.append({
            "id": inversion.id,
            "monto": Decimal(inversion.monto),
            "fecha_deposito": inversion.fecha_deposito,
            "interes_acumulado": interes_total,
            "interes_diario": interes_por_segundo * Decimal(86400),
            "puede_retirar_intereses": puede_retirar_intereses,
            "puede_retirar_capital": puede_retirar_capital,
            "fecha_proximo_retiro_intereses": inversion.fecha_proximo_retiro_intereses,
            "fecha_proximo_retiro_capital": inversion.fecha_proximo_retiro_capital,
            "dias_transcurridos": (ahora - inversion.fecha_deposito).days,
            "dias_faltantes_intereses": max(0, (inversion.fecha_proximo_retiro_intereses - ahora).days) if not puede_retirar_intereses else 0,
            "dias_faltantes_capital": max(0, (inversion.fecha_proximo_retiro_capital - ahora).days) if not puede_retirar_capital else 0
        })
    
    return {
        "total_invertido": Decimal(total_invertido),
        "total_intereses": Decimal(total_intereses),
        "total_intereses_disponibles": Decimal(total_intereses_disponibles),
        "inversiones": detalles_inversiones,
        "timestamp": ahora.isoformat()
    }

@router.post("/inversion/retirar/intereses")
def retirar_intereses(
    data: dict,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    """Retirar intereses acumulados de una inversión"""
    inversion_id = data.get("inversion_id")
    
    inversion = db.query(Inversion).filter(
        and_(
            Inversion.id == inversion_id,
            Inversion.usuario_id == current_user.id,
            Inversion.activa == True
        )
    ).first()
    
    if not inversion:
        raise HTTPException(status_code=404, detail="Inversión no encontrada")
    
    ahora = datetime.now(ZONE)  # Usar datetime.now con zona horaria
    
    # Verificar si puede retirar intereses
    if ahora < inversion.fecha_proximo_retiro_intereses:
        dias_faltantes = (inversion.fecha_proximo_retiro_intereses - ahora).days
        raise HTTPException(
            status_code=400, 
            detail=f"Debes esperar {dias_faltantes} días para retirar intereses"
        )
    
    # Calcular interés acumulado
    fecha_base = inversion.fecha_ultimo_retiro_intereses or inversion.fecha_deposito
    segundos_transcurridos = (ahora - fecha_base).total_seconds()
    
    # Asegurarse de que los segundos no sean negativos
    if segundos_transcurridos < 0:
        segundos_transcurridos = 0
    
    # Calcular interés acumulado
    tasa_segundo = Decimal(inversion.tasa_interes) / Decimal(100) / Decimal(365) / Decimal(86400)
    interes_por_segundo = Decimal(inversion.monto) * tasa_segundo
    interes_acumulado = interes_por_segundo * Decimal(segundos_transcurridos)
    
    # Sumar el interés previamente acumulado
    interes_acumulado_total = Decimal(inversion.interes_acumulado or 0) + interes_acumulado
    
    if interes_acumulado_total <= 0:
        raise HTTPException(status_code=400, detail="No hay intereses acumulados para retirar")
    
    # Actualizar saldo del usuario
    usuario = db.query(Usuario).filter(Usuario.id == current_user.id).first()
    usuario.saldo += interes_acumulado_total
    
    # Registrar retiro
    retiro = RetiroInversion(
        inversion_id=inversion.id,
        tipo="intereses",
        monto=float(interes_acumulado_total),
        fecha=ahora,
        detalles={
            "interes_acumulado": float(interes_acumulado_total),
            "dias_desde_ultimo_retiro": (ahora - fecha_base).days
        }
    )
    
    # Actualizar inversión
    inversion.interes_acumulado = 0  # Reiniciar interés acumulado
    inversion.fecha_ultimo_retiro_intereses = ahora
    inversion.fecha_proximo_retiro_intereses = ahora + timedelta(days=30)
    
    db.add(retiro)
    db.commit()
    db.refresh(usuario)
    
    return {
        "success": True,
        "message": f"✅ Retiro de intereses por ${interes_acumulado_total:,.0f} realizado con éxito",
        "monto_retirado": interes_acumulado_total,
        "nuevo_saldo": Decimal(usuario.saldo),
        "proximo_retiro_intereses": inversion.fecha_proximo_retiro_intereses.isoformat()
    }

@router.post("/inversion/retirar/capital")
def retirar_capital(
    data: dict,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    """Retirar el capital completo de una inversión"""
    inversion_id = data.get("inversion_id")
    
    inversion = db.query(Inversion).filter(
        and_(
            Inversion.id == inversion_id,
            Inversion.usuario_id == current_user.id,
            Inversion.activa == True
        )
    ).first()
    
    if not inversion:
        raise HTTPException(status_code=404, detail="Inversión no encontrada")
    
    ahora = datetime.now(ZONE)  # Usar datetime.now con zona horaria
    
    # Verificar si puede retirar capital
    if ahora < inversion.fecha_proximo_retiro_capital:
        dias_faltantes = (inversion.fecha_proximo_retiro_capital - ahora).days
        raise HTTPException(
            status_code=400, 
            detail=f"Debes esperar {dias_faltantes} días para retirar el capital"
        )
    
    # Calcular intereses finales usando segundos para mayor precisión
    fecha_inicio_calculo = inversion.fecha_ultimo_retiro_intereses or inversion.fecha_deposito
    segundos_transcurridos = (ahora - fecha_inicio_calculo).total_seconds()
    
    if segundos_transcurridos < 0:
        segundos_transcurridos = 0
    
    tasa_segundo = Decimal(inversion.tasa_interes) / Decimal(100) / Decimal(365) / Decimal(86400)
    interes_por_segundo = Decimal(inversion.monto) * tasa_segundo
    interes_final = interes_por_segundo * Decimal(segundos_transcurridos)
    
    # Sumar el interés previamente acumulado
    interes_final_total = Decimal(inversion.interes_acumulado or 0) + interes_final
    
    # Monto total a retirar (capital + intereses finales)
    monto_total = Decimal(inversion.monto) + interes_final_total
    
    # Actualizar saldo del usuario
    usuario = db.query(Usuario).filter(Usuario.id == current_user.id).first()
    usuario.saldo += monto_total
    
    # Registrar retiro
    retiro = RetiroInversion(
        inversion_id=inversion.id,
        tipo="capital",
        monto=float(monto_total),
        fecha=ahora,
        detalles={
            "capital": float(inversion.monto),
            "intereses_finales": float(interes_final_total),
            "total": float(monto_total)
        }
    )
    
    # Marcar inversión como inactiva
    inversion.activa = False
    inversion.fecha_ultimo_retiro_capital = ahora
    
    db.add(retiro)
    db.commit()
    db.refresh(usuario)
    
    return {
        "success": True,
        "message": f"✅ Retiro de capital por ${monto_total:,.0f} realizado con éxito",
        "capital": Decimal(inversion.monto),
        "intereses_finales": interes_final_total,
        "total_retirado": monto_total,
        "nuevo_saldo": Decimal(usuario.saldo)
    }

@router.get("/inversion/historial")
def obtener_historial_inversion(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    """Obtener historial completo de inversiones y retiros"""
    inversiones = db.query(Inversion).filter(
        Inversion.usuario_id == current_user.id
    ).order_by(Inversion.fecha_deposito.desc()).all()
    
    historial = []
    
    for inversion in inversiones:
        retiros = db.query(RetiroInversion).filter(
            RetiroInversion.inversion_id == inversion.id
        ).order_by(RetiroInversion.fecha.desc()).all()
        
        inversion_data = {
            "id": inversion.id,
            "monto": Decimal(inversion.monto),
            "fecha_deposito": inversion.fecha_deposito,
            "activa": inversion.activa,
            "tasa_interes": Decimal(inversion.tasa_interes),
            "retiros": [
                {
                    "tipo": retiro.tipo,
                    "monto": Decimal(retiro.monto),
                    "fecha": retiro.fecha,
                    "detalles": retiro.detalles
                }
                for retiro in retiros
            ]
        }
        
        historial.append(inversion_data)
    
    return {
        "total_inversiones": len(inversiones),
        "historial": historial
    }