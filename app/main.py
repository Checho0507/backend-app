from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from datetime import date, datetime, timedelta
import os

from .database import Base, SessionLocal, engine
from .services.vip import resolver_sorteo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# Routers
from .services.auth import router as auth_router
from .services.referidos import router as referidos_router
from .services.verify import router as verify_router
from .services.admin import router as admin_router
from .services.vip import router as vip_router
from .services.juegos.blackjack import router as blackjack_router
from .services.juegos.bonus import router as bonus_router
from .services.juegos.ruleta import router as ruleta_router
from .services.juegos.tragamonedas import router as tragamonedas_router
from .services.juegos.dados import router as dados_router
from .services.juegos.minas import router as minas_router
from .services.transacciones import router as transacciones_router

app = FastAPI(
    title="Gaming Platform API",
    description="API para plataforma de juegos con sistema de referidos",
    version="1.0.0"
)

# ------------------------
# CORS
# ------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción usa el dominio real
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------
# Archivos estáticos
# ------------------------
os.makedirs("recibos", exist_ok=True)
app.mount("/recibos", StaticFiles(directory="recibos"), name="recibos")

# ------------------------
# Scheduler
# ------------------------
scheduler = AsyncIOScheduler()

async def ejecutar_sorteo_automatico():
    try:
        print("🎰 Ejecutando sorteo automático...")
        db = SessionLocal()
        resolver_sorteo(db)
        db.close()
    except Exception as e:
        print(f"❌ Error en sorteo automático: {e}")

# ------------------------
# STARTUP EVENT (CLAVE)
# ------------------------
@app.on_event("startup")
async def startup_event():
    print("🚀 Iniciando aplicación...")

    # Crear tablas SOLO cuando la app ya arrancó
    Base.metadata.create_all(bind=engine)

    scheduler.add_job(
        ejecutar_sorteo_automatico,
        CronTrigger(hour=23, minute=59, timezone="America/Bogota"),
        id="sorteo_diario",
        replace_existing=True
    )
    scheduler.start()

# ------------------------
# SHUTDOWN EVENT
# ------------------------
@app.on_event("shutdown")
async def shutdown_event():
    scheduler.shutdown()

# ------------------------
# Rutas
# ------------------------
@app.get("/")
def root():
    return {"status": "ok"}

@app.get("/health")
def health_check():
    return {"status": "healthy"}

app.include_router(auth_router, tags=["Auth"])
app.include_router(referidos_router, tags=["Referidos"])
app.include_router(verify_router, prefix="/verificate", tags=["Verificación"])
app.include_router(admin_router, prefix="/admin", tags=["Admin"])
app.include_router(vip_router, prefix="/vip", tags=["VIP"])

app.include_router(bonus_router, prefix="/bonus-diario", tags=["Juegos"])
app.include_router(blackjack_router, prefix="/juegos/blackjack", tags=["Juegos"])
app.include_router(ruleta_router, prefix="/juegos/ruleta", tags=["Juegos"])
app.include_router(tragamonedas_router, prefix="/juegos/tragamonedas", tags=["Juegos"])
app.include_router(dados_router, prefix="/juegos/dados", tags=["Juegos"])
app.include_router(minas_router, prefix="/juegos/minas", tags=["Juegos"])

app.include_router(transacciones_router, prefix="/transacciones", tags=["Transacciones"])
