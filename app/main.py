"""
FastAPI Application - Sistema de Gaming y Referidos
Versión optimizada para Railway
"""

import os
from datetime import date, datetime, timedelta
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.database import Base, engine
from app.services.auth import router as auth_router
from app.services.referidos import router as referidos_router
from app.services.verify import router as verify_router
from app.services.admin import router as admin_router
from app.services.vip import router as vip_router
from app.services.vip import resolver_sorteo
from app.services.juegos.blackjack import router as blackjack_router
from app.services.juegos.bonus import router as bonus_router
from app.services.juegos.ruleta import router as ruleta_router
from app.services.juegos.tragamonedas import router as tragamonedas_router
from app.services.juegos.dados import router as dados_router
from app.services.juegos.minas import router as minas_router
from app.services.transacciones import router as transacciones_router
from app.services.juegos.aviator import router as aviator_router
from app.services.juegos.caraosello import router as caraosello_router
from app.services.juegos.cartamayor import router as cartamayor_router
from app.services.inversion import router as inversion_router
from app.services.juegos.piedrapapeltijera import router as piedrapapeltijera_router
from app.services.juegos.ruletaeuropea import router as ruletaeuropea_router

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session

# ============================================================================
# CONFIGURACIÓN INICIAL Y SCHEDULER
# ============================================================================

# Configuración de variables críticas para Railway
SECRET_KEY = os.environ.get("SECRET_KEY", "clave-desarrollo-solo-para-local")
ALGORITHM = os.environ.get("ALGORITHM", "HS256")

# Variables globales para la aplicación
NEXT_DRAW = datetime.utcnow() + timedelta(days=3)
PARTICIPANTS = []
scheduler = AsyncIOScheduler()

# ============================================================================
# FUNCIONES DE CICLO DE VIDA (LIFESPAN)
# ============================================================================

async def ejecutar_sorteo_automatico():
    """Ejecutar sorteo automáticamente cada día a las 11:59 PM hora Colombia"""
    try:
        print("🎰 [SCHEDULER] Iniciando sorteo automático...")
        from app.database import SessionLocal
        db = SessionLocal()
        try:
            resolver_sorteo(db)
            print("✅ [SCHEDULER] Sorteo completado exitosamente")
        except Exception as e:
            print(f"❌ [SCHEDULER] Error durante el sorteo: {e}")
        finally:
            db.close()
    except Exception as e:
        print(f"🔥 [SCHEDULER] Error crítico: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gestor del ciclo de vida de la aplicación.
    Se ejecuta al iniciar y al detener la aplicación.
    """
    # ==================== INICIO ====================
    print("🚀 Iniciando Gaming Platform API...")
    
    # Crear tablas en la base de datos (solo si no existen)
    try:
        Base.metadata.create_all(bind=engine)
        print("✅ Tablas de base de datos verificadas/creadas")
    except Exception as e:
        print(f"⚠️  Advertencia al crear tablas: {e}")
    
    # Configurar y arrancar el scheduler
    try:
        # Programar sorteo diario a las 23:59 hora Colombia
        scheduler.add_job(
            ejecutar_sorteo_automatico,
            CronTrigger(hour=23, minute=59, timezone='America/Bogota'),
            id='sorteo_diario',
            replace_existing=True
        )
        
        # Si estás en desarrollo, puedes agregar un trigger de prueba
        if os.environ.get("RAILWAY_ENVIRONMENT") != "production":
            scheduler.add_job(
                ejecutar_sorteo_automatico,
                'interval',
                minutes=5,
                id='sorteo_prueba',
                replace_existing=True
            )
            print("⏰ Scheduler de prueba configurado (cada 5 min)")
        
        scheduler.start()
        print("✅ Scheduler iniciado correctamente")
        
    except Exception as e:
        print(f"❌ Error al iniciar scheduler: {e}")
    
    # Mostrar información de configuración
    print(f"🔧 Entorno: {os.environ.get('RAILWAY_ENVIRONMENT', 'desarrollo')}")
    print(f"🌐 Host: 0.0.0.0")
    print(f"🔑 Puerto: {os.environ.get('PORT', '8000')}")
    
    yield  # La aplicación está en ejecución
    
    # ==================== FINALIZACIÓN ====================
    print("🛑 Deteniendo aplicación...")
    
    # Apagar el scheduler
    if scheduler.running:
        scheduler.shutdown()
        print("✅ Scheduler detenido")
    
    print("👋 Aplicación finalizada")

# ============================================================================
# CREACIÓN DE LA APLICACIÓN FASTAPI
# ============================================================================

app = FastAPI(
    title="Gaming Platform API",
    description="API para plataforma de juegos con sistema de referidos - Desplegado en Railway",
    version="2.0.0",
    lifespan=lifespan,  # Usamos el lifespan manager en lugar de eventos
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# ============================================================================
# CONFIGURACIÓN CORS (AJUSTADA PARA RAILWAY)
# ============================================================================

# Obtener dominios permitidos desde variables de entorno
allowed_origins = os.environ.get("ALLOWED_ORIGINS", "").split(",")
if not allowed_origins or allowed_origins == [""]:
    allowed_origins = [
        "http://localhost:5173",
        "https://betref.up.railway.app"
    ]

print(f"🌍 Orígenes CORS permitidos: {allowed_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=600
)

# ============================================================================
# ARCHIVOS ESTÁTICOS
# ============================================================================

# Crear directorio para recibos si no existe
os.makedirs("recibos", exist_ok=True)
app.mount("/recibos", StaticFiles(directory="recibos"), name="recibos")

# ============================================================================
# ENDPOINTS DE RAÍZ Y SALUD
# ============================================================================

@app.get("/")
def root():
    """Endpoint raíz - Información de la API"""
    return {
        "mensaje": "Gaming Platform API",
        "version": "2.0.0",
        "status": "activo",
        "entorno": os.environ.get("RAILWAY_ENVIRONMENT", "desarrollo"),
        "documentacion": "/docs",
        "health_check": "/health",
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/health")
def health_check():
    """Verificación de estado de la aplicación y base de datos"""
    from app.database import SessionLocal
    db_status = "unknown"
    
    try:
        db = SessionLocal()
        # Intenta una consulta simple
        db.execute("SELECT 1")
        db.close()
        db_status = "healthy"
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"
    
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "database": db_status,
        "environment": os.environ.get("RAILWAY_ENVIRONMENT", "development")
    }

@app.get("/info")
def info():
    """Información detallada del sistema (solo desarrollo)"""
    if os.environ.get("RAILWAY_ENVIRONMENT") == "production":
        return {"message": "Información restringida en producción"}
    
    return {
        "python_version": os.environ.get("PYTHON_VERSION"),
        "database_url": f"{os.environ.get('DATABASE_URL', '')[:30]}..." if os.environ.get('DATABASE_URL') else "not set",
        "port": os.environ.get("PORT", "8000"),
        "scheduler_jobs": len(scheduler.get_jobs()) if scheduler.running else 0,
        "current_time_utc": datetime.utcnow().isoformat(),
        "current_time_colombia": (datetime.utcnow() - timedelta(hours=5)).isoformat()
    }

# ============================================================================
# REGISTRO DE ROUTERS
# ============================================================================

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
app.include_router(caraosello_router, prefix="", tags=["Juegos"])
app.include_router(aviator_router, prefix="", tags=["Juegos"])
app.include_router(cartamayor_router, prefix="", tags=["Juegos"])
app.include_router(piedrapapeltijera_router, prefix="", tags=["Juegos"])
app.include_router(ruletaeuropea_router, prefix="", tags=["Juegos"])

# Rutas de transacciones
app.include_router(transacciones_router, prefix="/transacciones", tags=["Transacciones"])
# Rutas de inversiones
app.include_router(inversion_router, prefix="/inversiones", tags=["Inversiones"])


# ============================================================================
# PUNTO DE ENTRADA PARA RAILWAY
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    # Railway inyecta el puerto en la variable PORT
    port = int(os.environ.get("PORT", 8000))
    host = "0.0.0.0"
    
    print(f"🚀 Iniciando servidor en {host}:{port}")
    print(f"📚 Documentación disponible en http://{host}:{port}/docs")
    
    uvicorn.run(
        app, 
        host=host, 
        port=port,
        # Desactiva reload en producción
        reload=os.environ.get("RAILWAY_ENVIRONMENT") != "production"
    )