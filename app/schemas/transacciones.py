from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

# Esquemas para retiros
class RetiroCreate(BaseModel):
    monto: float = Field(..., gt=0, description="Monto a retirar (debe ser positivo)")
    metodo_retiro: str = Field(..., description="Método de retiro (nequi, daviplata, etc.)")
    cuenta_destino: str = Field(..., min_length=8, description="Cuenta destino del retiro")

class RetiroUpdate(BaseModel):
    estado: str = Field(..., description="Nuevo estado del retiro")
    observaciones: Optional[str] = Field(None, description="Observaciones del procesamiento")

class RetiroOut(BaseModel):
    id: int
    monto: float
    metodo_retiro: str
    cuenta_destino: str
    referencia: str
    estado: str
    observaciones: Optional[str]
    fecha_solicitud: datetime
    fecha_procesamiento: Optional[datetime]
    procesado_por: Optional[int]
    
    class Config:
        orm_mode = True