from typing import Optional, List
from pydantic import BaseModel, EmailStr, validator, Field
from .verificacion import VerificacionOut


class UsuarioCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    referido_por: Optional[int] = None

    @validator('username')
    def username_alphanumeric(cls, v):
        if not v.replace('_', '').isalnum():
            raise ValueError('El username solo puede contener letras, números y guiones bajos')
        return v

    @validator('password')
    def password_length(cls, v):
        if len(v) < 6:
            raise ValueError('La contraseña debe tener al menos 6 caracteres')
        return v


class UsuarioOut(BaseModel):
    id: int
    username: str
    email: EmailStr
    saldo: float
    verificado: bool
    verificacion_pendiente: bool
    referido_por: Optional[int] = None

    class Config:
        orm_mode = True


class UsuarioMeOut(BaseModel):
    id: int
    username: str
    email: EmailStr
    saldo: float
    verificado: bool

    class Config:
        orm_mode = True


class UsuarioConVerificacionesOut(UsuarioOut):
    verificaciones: List[VerificacionOut] = []


class ParticipanteOut(BaseModel):
    id: int
    username: str
    email: EmailStr
    saldo: float
    verificado: bool
    referido_por: Optional[int] = None
    referidos: List["ParticipanteOut"] = Field(default_factory=list)

    class Config:
        orm_mode = True


# Permitir recursividad en ParticipanteOut
ParticipanteOut.update_forward_refs()


from pydantic import BaseModel
from typing import List, Optional

class SubReferidoOut(BaseModel):
    username: str
    verificado: bool

    class Config:
        from_attributes = True

class ReferidoOut(BaseModel):
    username: str
    verificado: bool
    ganancia: int  # ✅ Ganancia calculada en backend
    referidos: List[SubReferidoOut]

    class Config:
        from_attributes = True