from datetime import datetime, timedelta
import json
import random
from typing import List
from fastapi.responses import JSONResponse
import pytz

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import and_, func
from decimal import Decimal

from ..models.usuario import Usuario
from ..models.resultado_sorteo import ResultadoSorteo, ParticipanteSorteo
from ..database import get_db
from ..api.auth import get_current_user, verificar_admin
from ..schemas.usuario import ParticipanteOut
from ..schemas.resultado_sorteo import GanadorOut, ResultadoSorteoOut

router = APIRouter()

ZONE = pytz.timezone("America/Bogota")  # Hora Colombia
NEXT_DRAW = None
sorteo_en_proceso = False  # Variable para prevenir ejecuciones simultáneas


def calcular_proximo_sorteo():
    """Calcula el próximo sorteo: todos los días a las 9:05 PM hora Colombia"""
    now_local = datetime.now(ZONE)
    hoy_905 = now_local.replace(hour=12, minute=15, second=0, microsecond=0)
    return hoy_905 if now_local < hoy_905 else hoy_905 + timedelta(days=1)


def obtener_fichas_por_costo(costo: float) -> int:
    """Calcula el número de fichas según el costo"""
    if costo == 10000:
        return 1
    elif costo == 20000:
        return 3
    elif costo == 50000:
        return 10
    elif costo == 100000:
        return 25
    else:
        return 1  # Por defecto


def verificar_y_ejecutar_sorteo_automatico(db: Session):
    """Verifica si es hora del sorteo y lo ejecuta automáticamente"""
    global NEXT_DRAW, sorteo_en_proceso
    
    if sorteo_en_proceso:
        return None
    
    now_local = datetime.now(ZONE)
    
    # Si no hay próxima fecha o ya pasó el tiempo, ejecutar sorteo
    if NEXT_DRAW is None or now_local >= NEXT_DRAW:
        try:
            sorteo_en_proceso = True
            print(f"🕒 Hora del sorteo automático: {now_local}")
            
            # Verificar si hay participantes
            participantes_activos = db.query(ParticipanteSorteo).filter(
                ParticipanteSorteo.es_activo == True
            ).count()
            
            if participantes_activos == 0:
                print("⚠️ No hay participantes para el sorteo automático")
                NEXT_DRAW = calcular_proximo_sorteo()
                return None
            
            # Ejecutar sorteo
            resultado = realizar_sorteo(db)
            
            # Programar próximo sorteo
            NEXT_DRAW = calcular_proximo_sorteo()
            print(f"✅ Sorteo automático ejecutado. Próximo sorteo: {NEXT_DRAW}")
            
            return resultado
            
        except Exception as e:
            print(f"❌ Error en sorteo automático: {str(e)}")
            return None
        finally:
            sorteo_en_proceso = False
    
    return None


def realizar_sorteo(db: Session):
    """Función principal para realizar el sorteo (reutilizable)"""
    try:
        # Obtener todos los participantes activos con sus fichas
        participantes_query = db.query(
            ParticipanteSorteo.usuario_id,
            Usuario.username,
            Usuario.verificado,
            Usuario.saldo,
            func.sum(ParticipanteSorteo.fichas).label('total_fichas')
        ).join(
            Usuario, ParticipanteSorteo.usuario_id == Usuario.id
        ).filter(
            ParticipanteSorteo.es_activo == True
        ).group_by(
            ParticipanteSorteo.usuario_id,
            Usuario.username,
            Usuario.verificado,
            Usuario.saldo
        ).all()
        
        if not participantes_query:
            raise HTTPException(status_code=400, detail="No hay participantes en el sorteo")

        # Crear lista de participantes con duplicación según fichas
        lista_para_sorteo = []
        for p in participantes_query:
            # Agregar el usuario_id tantas veces como fichas tenga
            for _ in range(p.total_fichas):
                lista_para_sorteo.append({
                    "id": p.usuario_id,
                    "username": p.username,
                    "verificado": p.verificado,
                    "saldo": p.saldo
                })
        
        total_fichas = len(lista_para_sorteo)
        print(f"🎰 Total de fichas en juego: {total_fichas}")
        
        # Seleccionar ganador
        ganador_data = random.choice(lista_para_sorteo)
        numero_ganador = ganador_data["id"]
        print(f"🎰 Número ganador generado: {numero_ganador}")
        
        # Buscar todos los usuarios que coincidan
        usuarios_ganadores = []
        ganadores_info = []
        
        for p in participantes_query:
            if p.usuario_id == numero_ganador:
                usuario_db = db.query(Usuario).filter(Usuario.id == p.usuario_id).first()
                if usuario_db:
                    saldo_anterior = usuario_db.saldo
                    premio = Decimal(500000)
                    usuario_db.saldo += premio
                    usuarios_ganadores.append(usuario_db)
                    
                    ganadores_info.append({
                        "id": p.usuario_id,
                        "username": p.username,
                        "saldo": float(usuario_db.saldo),
                        "verificado": p.verificado,
                        "premio": float(premio),
                        "saldo_anterior": float(saldo_anterior),
                        "fichas": p.total_fichas
                    })
                    print(f"💰 Ganador encontrado: {p.username} con {p.total_fichas} fichas")
        
        fecha_bogota = datetime.now(ZONE)
        
        # Crear registro del resultado
        resultado = ResultadoSorteo(
            fecha=fecha_bogota,
            numero_ganador=str(numero_ganador),
            ganadores=json.dumps(ganadores_info, ensure_ascii=False),
            total_participantes=len(participantes_query),
            total_ganadores=len(ganadores_info)
        )
        
        db.add(resultado)
        db.flush()
        
        # Actualizar participantes con el sorteo_id y marcar como inactivos
        db.query(ParticipanteSorteo).filter(
            ParticipanteSorteo.es_activo == True
        ).update({
            "sorteo_id": resultado.id,
            "es_activo": False
        })
        
        db.commit()
        
        # Refrescar usuarios ganadores
        for usuario in usuarios_ganadores:
            db.refresh(usuario)
        
        print(f"✅ Resultado guardado en BD - ID: {resultado.id}")
        print(f"📊 Total participantes: {len(participantes_query)} | Total fichas: {total_fichas} | Ganadores: {len(ganadores_info)}")
        
        return {
            "success": True,
            "numero_ganador": numero_ganador,
            "ganadores": ganadores_info,
            "total_participantes": len(participantes_query),
            "total_fichas": total_fichas,
            "total_ganadores": len(ganadores_info),
            "fecha_sorteo": fecha_bogota.isoformat()
        }

    except Exception as e:
        db.rollback()
        print(f"❌ Error al realizar sorteo: {str(e)}")
        raise


# Inicializar la fecha del próximo sorteo
NEXT_DRAW = calcular_proximo_sorteo()


@router.post("/vip/participar")
def participar_sorteo_vip(
    data: dict,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    """Inscribirse en sorteo VIP con costo dinámico"""
    costo_vip = data.get("costo")
    if not isinstance(costo_vip, (int, float)) or costo_vip <= 0:
        raise HTTPException(status_code=400, detail="Costo inválido")

    usuario = db.query(Usuario).filter(Usuario.id == current_user.id).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if usuario.saldo < costo_vip:
        raise HTTPException(status_code=400, detail=f"Saldo insuficiente. Se requieren ${costo_vip}")

    # Verificar si ya está inscrito en el sorteo activo
    participacion_existente = db.query(ParticipanteSorteo).filter(
        and_(
            ParticipanteSorteo.usuario_id == usuario.id,
            ParticipanteSorteo.es_activo == True
        )
    ).first()
    
    if participacion_existente:
        raise HTTPException(status_code=400, detail="Ya estás inscrito en el sorteo VIP actual")

    # Calcular fichas
    fichas = obtener_fichas_por_costo(costo_vip)

    # Descontar saldo
    usuario.saldo -= costo_vip
    db.commit()

    # Crear registro de participante
    participante = ParticipanteSorteo(
        usuario_id=usuario.id,
        costo=costo_vip,
        fichas=fichas,
        fecha_participacion=datetime.utcnow(),
        sorteo_id=1,
        es_activo=True
    )
    
    db.add(participante)
    db.commit()
    db.refresh(usuario)
    db.refresh(participante)

    return {
        "mensaje": f"Te has inscrito correctamente al sorteo VIP 🎉 Se descontaron ${costo_vip} por {fichas} ficha(s).",
        "nuevo_saldo": float(usuario.saldo),
        "fichas_obtenidas": fichas,
        "id_participacion": participante.id
    }


@router.get("/vip/participantes", response_model=List[ParticipanteOut])
def listar_participantes_vip(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(verificar_admin)
):
    """Listar participantes del sorteo VIP (solo admin)"""
    participantes = db.query(Usuario).join(
        ParticipanteSorteo, ParticipanteSorteo.usuario_id == Usuario.id
    ).filter(ParticipanteSorteo.es_activo == True).all()
    
    return participantes


@router.get("/vip/participantes/detalle")
def listar_participantes_detalle(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(verificar_admin)
):
    """Listar participantes con detalles de fichas (solo admin)"""
    participantes = db.query(
        Usuario.id,
        Usuario.username,
        Usuario.verificado,
        func.sum(ParticipanteSorteo.fichas).label('total_fichas'),
        func.count(ParticipanteSorteo.id).label('total_participaciones')
    ).join(
        ParticipanteSorteo, ParticipanteSorteo.usuario_id == Usuario.id
    ).filter(
        ParticipanteSorteo.es_activo == True
    ).group_by(
        Usuario.id, Usuario.username, Usuario.verificado
    ).all()
    
    return [
        {
            "id": p.id,
            "username": p.username,
            "verificado": p.verificado,
            "total_fichas": p.total_fichas,
            "total_participaciones": p.total_participaciones
        }
        for p in participantes
    ]


@router.post("/vip/resolver")
def resolver_sorteo(db: Session = Depends(get_db)):
    """Resolver sorteo VIP manualmente"""
    try:
        resultado = realizar_sorteo(db)
        global NEXT_DRAW
        NEXT_DRAW = calcular_proximo_sorteo()
        
        return JSONResponse({
            **resultado,
            "proximo_sorteo": NEXT_DRAW.isoformat()
        })

    except Exception as e:
        print(f"❌ Error al resolver sorteo: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")


@router.get("/vip/next_draw")
def get_next_draw(db: Session = Depends(get_db)):
    """Obtener información del próximo sorteo"""
    global NEXT_DRAW
    
    # Verificar y ejecutar sorteo automático si es la hora
    verificar_y_ejecutar_sorteo_automatico(db)
    
    # Si NEXT_DRAW no está definido o ya pasó, calcular próximo
    if NEXT_DRAW is None or datetime.now(ZONE) >= NEXT_DRAW:
        NEXT_DRAW = calcular_proximo_sorteo()
    
    # Contar participantes activos y fichas
    total_participantes = db.query(ParticipanteSorteo).filter(
        ParticipanteSorteo.es_activo == True
    ).count()
    
    total_fichas = db.query(func.sum(ParticipanteSorteo.fichas)).filter(
        ParticipanteSorteo.es_activo == True
    ).scalar() or 0

    return {
        "next_draw": NEXT_DRAW.isoformat(),
        "participantes_actuales": total_participantes,
        "fichas_actuales": total_fichas,
        "timezone": "America/Bogota"
    }


@router.get("/vip/results", response_model=List[ResultadoSorteoOut])
def get_results(db: Session = Depends(get_db)):
    try:
        resultados_db = db.query(ResultadoSorteo).order_by(ResultadoSorteo.fecha.desc()).limit(50).all()
        print(f"📊 Resultados encontrados en BD: {len(resultados_db)}")

        resultados = []
        for res in resultados_db:
            ganadores_data = []
            if res.ganadores:
                try:
                    ganadores_data = json.loads(res.ganadores)
                except json.JSONDecodeError:
                    ganadores_data = []

            ganadores_out = [GanadorOut(**g) for g in ganadores_data]
            resultados.append(ResultadoSorteoOut(
                id=res.id,
                fecha=res.fecha,
                numero_ganador=res.numero_ganador,
                ganadores=ganadores_out,
                total_participantes=res.total_participantes,
                total_ganadores=res.total_ganadores
            ))

        return resultados

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener resultados: {str(e)}")


@router.post("/vip/ejecutar_sorteo")
def ejecutar_sorteo_manual(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(verificar_admin)
):
    """Ejecutar sorteo manualmente (solo admin)"""
    return resolver_sorteo(db)


@router.delete("/vip/limpiar")
def limpiar_participantes(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(verificar_admin)
):
    """Limpiar todos los participantes activos (solo admin)"""
    try:
        # Marcar todos los participantes activos como inactivos
        db.query(ParticipanteSorteo).filter(
            ParticipanteSorteo.es_activo == True
        ).update({"es_activo": False})
        db.commit()
        
        return {"mensaje": "Todos los participantes han sido limpiados", "success": True}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al limpiar participantes: {str(e)}")