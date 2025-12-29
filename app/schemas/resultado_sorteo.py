# app/schemas/resultado_sorteo.py
from typing import List
from pydantic import BaseModel, Field
from datetime import datetime

class GanadorOut(BaseModel):
    id: int
    username: str
    saldo: float
    verificado: bool = False
    premio: int = Field(default=500000, description="Premio ganado")
    saldo_anterior: float = Field(default=0, description="Saldo antes del premio")

    class Config:
        from_attributes = True

class ResultadoSorteoOut(BaseModel):
    id: int
    fecha: datetime
    numero_ganador: int
    ganadores: List[GanadorOut]
    
    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
