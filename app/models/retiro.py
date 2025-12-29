# app/models.py (agregar estos modelos)
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from ..database import Base

class Retiro(Base):
    __tablename__ = "retiros"
    
    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"))
    monto = Column(Float, nullable=False)
    metodo_retiro = Column(String, nullable=False)
    cuenta_destino = Column(String, nullable=False)
    tipo_cuenta = Column(String, default="ahorros")
    banco = Column(String, nullable=True)
    comision = Column(Float, nullable=False)
    total = Column(Float, nullable=False)
    referencia = Column(String, unique=True, index=True)
    estado = Column(String, default="PENDIENTE")  # PENDIENTE, APROBADO, RECHAZADO
    fecha_solicitud = Column(DateTime, default=datetime.now)
    fecha_procesamiento = Column(DateTime, nullable=True)
    
    usuario = relationship("Usuario", back_populates="retiros")
