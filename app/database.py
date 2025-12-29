# app/database.py
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
import os
from dotenv import load_dotenv

# 🔹 Cargar variables de entorno
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")

if not DATABASE_URL:
    raise ValueError("❌ La variable de entorno DATABASE_URL no está configurada.")

# 🔹 Configuración del motor de base de datos
engine = create_engine(DATABASE_URL)

# 🔹 Sesión para interactuar con la base de datos
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 🔹 Base para los modelos
Base = declarative_base()

# -------------------------------
# Función para obtener sesión de DB
# -------------------------------
def get_db() -> Session: # type: ignore
    """Dependencia para obtener una sesión de base de datos."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

