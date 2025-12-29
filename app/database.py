# app/database.py
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
import os
from urllib.parse import urlparse

# 🔹 Obtener DATABASE_URL de Railway (Railway la inyecta automáticamente)
DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("❌ DATABASE_URL no encontrada. Verifica las variables en Railway.")

# 🔹 CONVERSIÓN CRÍTICA: Railway usa 'postgres://', SQLAlchemy necesita 'postgresql://'
# Además, añadimos parámetros SSL para Railway
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# 🔹 Añadir parámetros SSL (obligatorio en Railway)
# Parseamos la URL para mantener credenciales intactas
parsed_url = urlparse(DATABASE_URL)
query_params = "sslmode=require"
if parsed_url.query:
    DATABASE_URL = f"{DATABASE_URL.split('?')[0]}?{query_params}"
else:
    DATABASE_URL = f"{DATABASE_URL}?{query_params}"

print(f"📡 Conectando a: {parsed_url.hostname}:{parsed_url.port}")  # Para debug

# 🔹 Configuración del motor con parámetros optimizados
engine = create_engine(
    DATABASE_URL,
    pool_size=10,  # Tamaño del pool de conexiones
    max_overflow=20,  # Conexiones adicionales cuando el pool está lleno
    pool_pre_ping=True,  # Verifica conexiones antes de usarlas
    echo=False  # Cambia a True para ver queries SQL en logs (solo desarrollo)
)

# 🔹 Sesión para interactuar con la base de datos
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 🔹 Base para los modelos
Base = declarative_base()

# -------------------------------
# Función para obtener sesión de DB
# -------------------------------
def get_db():
    """Dependencia para obtener una sesión de base de datos."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()