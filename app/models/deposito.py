# app/models.py (agregar estos modelos)
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from ..database import Base

class Deposito(Base):
    __tablename__ = "depositos"
    
    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"))
    monto = Column(Float, nullable=False)
    metodo_pago = Column(String, nullable=False)
    referencia = Column(String, unique=True, index=True)
    estado = Column(String, default="PENDIENTE")  # PENDIENTE, APROBADO, RECHAZADO
    comprobante_url = Column(String, nullable=True)
    fecha_solicitud = Column(DateTime, default=datetime.now)
    fecha_procesamiento = Column(DateTime, nullable=True)
    
    usuario = relationship("Usuario", back_populates="depositos")