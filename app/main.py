# app/main.py
"""
FastAPI Application - Sistema de Gaming y Referidos
Versión corregida con eliminación de duplicados y mejoras estructurales
"""

from datetime import date, datetime, timedelta
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from app.services.auth import router as auth_router

# Imports locales
from .database import Base, SessionLocal, engine
from .services.auth import router as auth_router
from .services.referidos import router as referidos_router
from .services.verify import router as verify_router
from .services.admin import router as admin_router
from .services.vip import router as vip_router
from .services.vip import resolver_sorteo
from .services.juegos.blackjack import router as blackjack_router
from .services.juegos.bonus import router as bonus_router
from .services.juegos.ruleta import router as ruleta_router
from .services.juegos.tragamonedas import router as tragamonedas_router
from .services.juegos.dados import router as dados_router
from .services.juegos.minas import router as minas_router
from .services.transacciones import router as transacciones_router

import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# En tu archivo main.py
scheduler = AsyncIOScheduler()

db = ""

async def ejecutar_sorteo_automatico():
    """Ejecutar sorteo automáticamente cada día a las 7:15 PM"""
    try:
        # Aquí tendrías que importar y llamar a resolver_sorteo
        # Esto requiere acceso a la sesión de base de datos
        print("🎰 Ejecutando sorteo automático...")
        db = SessionLocal()
        resolver_sorteo(db)
        db.close()
    except Exception as e:
        print(f"❌ Error en sorteo automático: {e}")

# Programar sorteo diario a las 11:59 PM hora Colombia
scheduler.add_job(
    ejecutar_sorteo_automatico,
    CronTrigger(hour=23, minute=59, timezone='America/Bogota'),
    id='sorteo_diario'
)

# Iniciar el scheduler
scheduler.start()


# Crear tablas en base de datos
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Gaming Platform API",
    description="API para plataforma de juegos con sistema de referidos",
    version="1.0.0"
)

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000"  # Por si usas otro puerto
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=[
        "Content-Type",
        "Authorization",
        "Accept",
        "Origin",
        "X-Requested-With",
        "Access-Control-Request-Method",
        "Access-Control-Request-Headers"
    ],
    expose_headers=["*"],
    max_age=3600
)

# Archivos estáticos (ejemplo para recibos)
os.makedirs("recibos", exist_ok=True)
app.mount("/recibos", StaticFiles(directory="recibos"), name="recibos")

# Configuración OAuth2
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

NEXT_DRAW = datetime.utcnow() + timedelta(days=3)
PARTICIPANTS = []


# ------------------------
# Endpoints raíz y salud
# ------------------------

@app.get("/")
def root():
    """Endpoint raíz - Información básica de la API"""
    return {
        "mensaje": "Gaming Platform API",
        "version": "1.0.0",
        "status": "activo",
        "endpoints_principales": [
            "/docs",
            "/juegos",
            "/register",
            "/login"
        ]
    }

@app.get("/health")
def health_check():
    """Verificación de estado de la aplicación"""
    return {"status": "healthy", "timestamp": date.today().isoformat()}

# ------------------------
# Incluir routers externos
# ------------------------

# Rutas de autenticación y usuarios
app.include_router(auth_router, tags=["Autenticación"])

# Rutas de referidos
app.include_router(referidos_router, tags=["Referidos"])

# Rutas de verificación
app.include_router(verify_router, prefix="/verificate", tags=["Verificación"])

# Rutas de administración
app.include_router(admin_router, prefix="/admin", tags=["Administración"])

# Rutas de VIP
app.include_router(vip_router, prefix="/vip", tags=["VIP"])

# Rutas de juegos
app.include_router(bonus_router, prefix="/bonus-diario", tags=["Juegos"])

app.include_router(blackjack_router, prefix="/juegos/blackjack", tags=["Juegos"])
app.include_router(ruleta_router, prefix="/juegos/ruleta", tags=["Juegos"])
app.include_router(tragamonedas_router, prefix="/juegos/tragamonedas", tags=["Juegos"])
app.include_router(dados_router, prefix="/juegos/dados", tags=["Juegos"])
app.include_router(minas_router, prefix="/juegos/minas", tags=["Juegos"])

# Rutas de transacciones
app.include_router(transacciones_router, prefix="/transacciones", tags=["Transacciones"])

# ------------------------
# Configuración para desarrollo
# ------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)