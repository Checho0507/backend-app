from sqlalchemy import Column, Integer, Float, String, DateTime, Boolean, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from ..database import Base

class Inversion(Base):
    __tablename__ = "inversiones"
    
    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"))
    monto = Column(Float, nullable=False)  # Monto depositado
    interes_acumulado = Column(Float, default=0)  # Intereses acumulados
    fecha_deposito = Column(DateTime, default=datetime.utcnow)
    fecha_ultimo_retiro_intereses = Column(DateTime, nullable=True)
    fecha_ultimo_retiro_capital = Column(DateTime, nullable=True)
    fecha_proximo_retiro_intereses = Column(DateTime, nullable=True)
    fecha_proximo_retiro_capital = Column(DateTime, nullable=True)
    activa = Column(Boolean, default=True)
    tasa_interes = Column(Float, default=300.0)  # 300% anual
    
    # Relaciones
    usuario = relationship("Usuario", back_populates="inversiones")
    retiros = relationship("RetiroInversion", back_populates="inversion")

class RetiroInversion(Base):
    __tablename__ = "retiros_inversiones"
    
    id = Column(Integer, primary_key=True, index=True)
    inversion_id = Column(Integer, ForeignKey("inversiones.id"))
    tipo = Column(String)  # 'intereses' o 'capital'
    monto = Column(Float, nullable=False)
    fecha = Column(DateTime, default=datetime.utcnow)
    detalles = Column(JSON, nullable=True)
    
    # Relaciones
    inversion = relationship("Inversion", back_populates="retiros")