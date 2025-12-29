from sqlalchemy import Column, ForeignKey, Integer, String, DateTime, Float, Boolean
from datetime import datetime
from sqlalchemy.orm import relationship
import pytz
from ..database import Base

class ResultadoSorteo(Base):
    __tablename__ = "resultados_sorteo"
    
    id = Column(Integer, primary_key=True, index=True)
    fecha = Column(DateTime, nullable=False)
    numero_ganador = Column(String, nullable=False)  # Cambiado a String para mejor manejo
    ganadores = Column(String, nullable=False)  # JSON serializado
    total_participantes = Column(Integer, nullable=False, default=0)
    total_ganadores = Column(Integer, nullable=False, default=0)

    def __repr__(self):
        return f"<ResultadoSorteo(id={self.id}, numero_ganador={self.numero_ganador})>"


class ParticipanteSorteo(Base):
    __tablename__ = "participantes_sorteo"
    
    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    costo = Column(Float, nullable=False)
    fichas = Column(Integer, nullable=False, default=1)  # Número de participaciones
    fecha_participacion = Column(DateTime, default=datetime.utcnow)
    sorteo_id = Column(Integer, ForeignKey("resultados_sorteo.id"), nullable=True)  # NULL hasta que se resuelve
    es_activo = Column(Boolean, default=True)  # True si aún está participando en sorteo activo
    
    # Relaciones
    sorteo = relationship("ResultadoSorteo")
    usuario = relationship("Usuario", backref="participaciones")