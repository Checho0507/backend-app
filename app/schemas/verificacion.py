from pydantic import BaseModel
from datetime import datetime

class VerificacionCreate(BaseModel):
    pass  # Solo archivo en frontend

class VerificacionUpdate(BaseModel):
    estado: str  # pendiente, aceptado, rechazado

class VerificacionOut(BaseModel):
    id: int
    usuario_id: int
    archivo_url: str
    estado: str
    creado_en: datetime

    class Config:
        from_attributes = True
