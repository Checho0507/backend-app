from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Numeric, Date
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class Usuario(Base):
    __tablename__ = "usuarios"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    referido_por = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    saldo = Column(Numeric(10, 2), default=0.00)
    verificado = Column(Boolean, default=False)
    verificacion_pendiente = Column(Boolean, default=False)
    fecha_registro = Column(DateTime, default=datetime.utcnow)
    ultima_recompensa = Column(Date, nullable=True)

    # Relaciones
    referidos = relationship("Usuario", backref="padrino", remote_side=[id])
    depositos = relationship("Deposito", back_populates="usuario", cascade="all, delete-orphan") 
    retiros = relationship("Retiro", back_populates="usuario", cascade="all, delete-orphan")
    verificaciones = relationship("Verificacion", back_populates="usuario", cascade="all, delete")
    inversiones = relationship("Inversion", back_populates="usuario", cascade="all, delete-orphan")