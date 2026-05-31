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

ZONE = pytz.timezone("America/Bogota")
NEXT_DRAW = None
sorteo_en_proceso = False

TOTAL_SLOTS = 100  # Siempre 100 números en el sorteo


def calcular_proximo_sorteo():
    """Calcula el próximo sorteo: todos los días a las 9:05 PM hora Colombia"""
    now_local = datetime.now(ZONE)
    hoy_905 = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
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
        return 1


def verificar_y_ejecutar_sorteo_automatico(db: Session):
    """Verifica si es hora del sorteo y lo ejecuta automáticamente.
    Siempre registra el resultado, incluso si no hay participantes."""
    global NEXT_DRAW, sorteo_en_proceso

    if sorteo_en_proceso:
        return None

    now_local = datetime.now(ZONE)

    if NEXT_DRAW is None or now_local >= NEXT_DRAW:
        try:
            sorteo_en_proceso = True
            print(f"🕒 Hora del sorteo automático: {now_local}")

            resultado = realizar_sorteo(db)

            NEXT_DRAW = calcular_proximo_sorteo()
            print(f"✅ Sorteo automático ejecutado. Próximo sorteo: {NEXT_DRAW}")

            return resultado

        except Exception as e:
            print(f"❌ Error en sorteo automático: {str(e)}")
            NEXT_DRAW = calcular_proximo_sorteo()
            return None
        finally:
            sorteo_en_proceso = False

    return None


def realizar_sorteo(db: Session):
    """Realiza el sorteo con 100 slots numerados.
    Siempre registra el resultado, aunque no haya participantes o nadie gane."""
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

        total_participantes = len(participantes_query)
        print(f"🎰 Participantes en el sorteo: {total_participantes}")

        # Construir los 100 slots: cada posición puede estar vacía (None) o pertenecer a un usuario
        slots = [None] * TOTAL_SLOTS
        slot_actual = 0

        for p in participantes_query:
            fichas_disponibles = min(int(p.total_fichas), TOTAL_SLOTS - slot_actual)
            for _ in range(fichas_disponibles):
                if slot_actual < TOTAL_SLOTS:
                    slots[slot_actual] = {
                        "id": p.usuario_id,
                        "username": p.username,
                        "verificado": p.verificado,
                        "saldo": float(p.saldo)
                    }
                    slot_actual += 1

        fichas_ocupadas = slot_actual
        print(f"🎰 Slots ocupados: {fichas_ocupadas}/{TOTAL_SLOTS}")

        # Sorteo: elegir número entre 1 y 100
        numero_sorteado = random.randint(1, TOTAL_SLOTS)
        ganador_data = slots[numero_sorteado - 1]  # None si el slot está vacío

        print(f"🎰 Número sorteado: {numero_sorteado} — Slot: {'OCUPADO' if ganador_data else 'VACÍO'}")

        fecha_bogota = datetime.now(ZONE)
        ganadores_info = []

        if ganador_data is not None:
            # Hay ganador
            usuario_db = db.query(Usuario).filter(Usuario.id == ganador_data["id"]).first()
            if usuario_db:
                saldo_anterior = float(usuario_db.saldo)
                premio = Decimal(500000)
                usuario_db.saldo += premio

                ganadores_info.append({
                    "id": ganador_data["id"],
                    "username": ganador_data["username"],
                    "saldo": float(usuario_db.saldo),
                    "verificado": ganador_data["verificado"],
                    "premio": float(premio),
                    "saldo_anterior": saldo_anterior,
                    "fichas": next(
                        (int(p.total_fichas) for p in participantes_query if p.usuario_id == ganador_data["id"]),
                        0
                    )
                })
                print(f"💰 Ganador: {ganador_data['username']} — Premio: $500,000")
        else:
            print(f"⚠️ Número {numero_sorteado} cayó en slot vacío — Nadie ganó este sorteo")

        # Crear registro del resultado (SIEMPRE se guarda)
        resultado = ResultadoSorteo(
            fecha=fecha_bogota,
            numero_ganador=str(numero_sorteado),
            ganadores=json.dumps(ganadores_info, ensure_ascii=False),
            total_participantes=total_participantes,
            total_ganadores=len(ganadores_info)
        )

        db.add(resultado)
        db.flush()

        # Marcar todos los participantes activos como inactivos y asignarles el sorteo
        if total_participantes > 0:
            db.query(ParticipanteSorteo).filter(
                ParticipanteSorteo.es_activo == True
            ).update({
                "sorteo_id": resultado.id,
                "es_activo": False
            })

        db.commit()

        if ganadores_info:
            usuario_ganador = db.query(Usuario).filter(Usuario.id == ganadores_info[0]["id"]).first()
            if usuario_ganador:
                db.refresh(usuario_ganador)

        print(f"✅ Resultado guardado — ID: {resultado.id} | Número: {numero_sorteado} | Ganadores: {len(ganadores_info)}")

        return {
            "success": True,
            "numero_ganador": numero_sorteado,
            "hay_ganador": len(ganadores_info) > 0,
            "ganadores": ganadores_info,
            "total_participantes": total_participantes,
            "fichas_ocupadas": fichas_ocupadas,
            "total_slots": TOTAL_SLOTS,
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

    fichas = obtener_fichas_por_costo(costo_vip)

    # Verificar que aún hay slots disponibles (máx 100)
    fichas_actuales = db.query(func.sum(ParticipanteSorteo.fichas)).filter(
        ParticipanteSorteo.es_activo == True
    ).scalar() or 0

    if fichas_actuales + fichas > TOTAL_SLOTS:
        slots_restantes = TOTAL_SLOTS - fichas_actuales
        raise HTTPException(
            status_code=400,
            detail=f"No hay suficientes slots disponibles. Quedan {slots_restantes} de {TOTAL_SLOTS}."
        )

    usuario.saldo -= costo_vip
    db.commit()

    participante = ParticipanteSorteo(
        usuario_id=usuario.id,
        costo=costo_vip,
        fichas=fichas,
        fecha_participacion=datetime.utcnow(),
        sorteo_id=None,
        es_activo=True
    )

    db.add(participante)
    db.commit()
    db.refresh(usuario)
    db.refresh(participante)

    slots_restantes_post = TOTAL_SLOTS - (fichas_actuales + fichas)

    return {
        "mensaje": f"✅ ¡Inscrito al sorteo VIP! Se descontaron ${int(costo_vip):,} por {fichas} ficha(s). Ocupas los slots {int(fichas_actuales)+1}–{int(fichas_actuales)+fichas} de {TOTAL_SLOTS}.",
        "nuevo_saldo": float(usuario.saldo),
        "fichas_obtenidas": fichas,
        "slots_asignados": f"{int(fichas_actuales)+1}–{int(fichas_actuales)+fichas}",
        "slots_restantes": slots_restantes_post,
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

    verificar_y_ejecutar_sorteo_automatico(db)

    if NEXT_DRAW is None or datetime.now(ZONE) >= NEXT_DRAW:
        NEXT_DRAW = calcular_proximo_sorteo()

    total_participantes = db.query(ParticipanteSorteo).filter(
        ParticipanteSorteo.es_activo == True
    ).count()

    total_fichas = db.query(func.sum(ParticipanteSorteo.fichas)).filter(
        ParticipanteSorteo.es_activo == True
    ).scalar() or 0

    return {
        "next_draw": NEXT_DRAW.isoformat(),
        "participantes_actuales": total_participantes,
        "fichas_actuales": int(total_fichas),
        "slots_disponibles": TOTAL_SLOTS - int(total_fichas),
        "total_slots": TOTAL_SLOTS,
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
        db.query(ParticipanteSorteo).filter(
            ParticipanteSorteo.es_activo == True
        ).update({"es_activo": False})
        db.commit()

        return {"mensaje": "Todos los participantes han sido limpiados", "success": True}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al limpiar participantes: {str(e)}")
