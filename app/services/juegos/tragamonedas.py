import random
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from ...database import get_db
from ...api.auth import get_current_user
from ...models.usuario import Usuario

router = APIRouter()

SIMBOLOS = ["🍒", "🍋", "🍊", "🍉", "⭐", "🔔", "🍇", "7️⃣"]

# Tabla de multiplicadores por símbolo (como en el frontend)
TABLA_PAGOS = {
    "7️⃣": 100,  # Multiplicador por la apuesta
    "🍇": 50,
    "🔔": 25,
    "⭐": 5,
    "🍉": 4,
    "🍊": 3,
    "🍋": 2,
    "🍒": 1,
}

# Apuestas permitidas
APUESTAS_PERMITIDAS = [100, 500, 1000, 2000, 5000]

# Probabilidades personalizadas para cada premio
PROB_PREMIOS = {
    ("🍒", "🍒", "🍒"): 0.35,    # Más común, menor premio
    ("🍋", "🍋", "🍋"): 0.25,
    ("🍊", "🍊", "🍊"): 0.20,
    ("🍉", "🍉", "🍉"): 0.10,
    ("⭐", "⭐", "⭐"): 0.08,
    ("🔔", "🔔", "🔔"): 0.014,
    ("🍇", "🍇", "🍇"): 0.005,
    ("7️⃣", "7️⃣", "7️⃣"): 0.001,   # Más raro, mayor premio
}

@router.get("/juegos/tragamonedas/apuestas-permitidas")
def obtener_apuestas_permitidas():
    """Endpoint para obtener las apuestas permitidas"""
    return {
        "apuestas_permitidas": APUESTAS_PERMITIDAS
    }

@router.post("/juegos/tragamonedas")
def jugar_tragamonedas(
    apuesta: int = Query(..., description="Monto de la apuesta"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    # Validar que la apuesta esté permitida
    if apuesta not in APUESTAS_PERMITIDAS:
        raise HTTPException(
            status_code=400, 
            detail=f"Apuesta no válida. Apuestas permitidas: {APUESTAS_PERMITIDAS}"
        )

    usuario = db.query(Usuario).filter(Usuario.id == current_user.id).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if usuario.saldo < apuesta:
        raise HTTPException(status_code=400, detail="Saldo insuficiente para apostar")

    # Descontar la apuesta
    usuario.saldo -= apuesta

    # Probabilidad de premio ajustable según la apuesta
    PROBABILIDAD_DE_PREMIO = 0.30  # 30% base de probabilidad de premio
    
    # Bonus de probabilidad para apuestas más altas (opcional)
    if apuesta >= 2000:
        PROBABILIDAD_DE_PREMIO += 0.05  # +5% para apuestas altas
    elif apuesta >= 5000:
        PROBABILIDAD_DE_PREMIO += 0.10  # +10% para apuestas muy altas

    # Decidir si hay premio o no
    if random.random() < PROBABILIDAD_DE_PREMIO:
        # Elegir un premio según sus probabilidades internas
        premios_posibles = list(PROB_PREMIOS.keys())
        pesos = list(PROB_PREMIOS.values())
        resultado = random.choices(premios_posibles, weights=pesos, k=1)[0]
        
        # Calcular ganancia basada en el multiplicador y la apuesta
        simbolo_ganador = resultado[0]  # Todos los símbolos son iguales en un premio
        multiplicador = TABLA_PAGOS[simbolo_ganador]
        ganancia = multiplicador * apuesta
        
    else:
        # Generar un resultado que no sea premio
        while True:
            resultado = tuple(random.choices(SIMBOLOS, k=3))
            # Verificar que no sea una combinación ganadora
            if not (resultado[0] == resultado[1] == resultado[2]):
                break
        ganancia = 0

    # Añadir ganancia al saldo
    usuario.saldo += ganancia

    # Preparar mensaje
    if ganancia > 0:
        mensaje = f"🎉 ¡GANASTE! {' '.join(resultado)} - Premio: ${ganancia:,}"
    else:
        mensaje = f"❌ Sin suerte esta vez: {' '.join(resultado)}"

    db.commit()
    db.refresh(usuario)

    return {
        "resultado": list(resultado),  # Convertir tupla a lista para JSON
        "ganancia": ganancia,
        "nuevo_saldo": usuario.saldo,
        "mensaje": mensaje,
        "apuesta_realizada": apuesta,
        "multiplicador": TABLA_PAGOS.get(resultado[0], 0) if ganancia > 0 else 0
    }

@router.get("/juegos/tragamonedas/estadisticas")
def obtener_estadisticas_tragamonedas():
    """Endpoint opcional para mostrar estadísticas del juego"""
    return {
        "simbolos_disponibles": SIMBOLOS,
        "tabla_multiplicadores": TABLA_PAGOS,
        "apuestas_permitidas": APUESTAS_PERMITIDAS,
        "probabilidad_base_premio": 0.30,
        "premios_posibles": {
            f"{k[0]} {k[1]} {k[2]}": {
                "probabilidad": f"{v*100:.1f}%",
                "multiplicador": TABLA_PAGOS[k[0]]
            }
            for k, v in PROB_PREMIOS.items()
        }
    }
