from pydantic import BaseModel
from typing import Optional

# Esquema para crear y leer categorías
class CategoriaBase(BaseModel):
    nombre: str

class CategoriaRespuesta(CategoriaBase):
    id: int
    class Config:
        from_attributes = True

# Esquema para leer pantalones
class PantalonRespuesta(BaseModel):
    id: int
    nombre: str
    descripcion: Optional[str] = None
    precio: float
    imagen_url: str
    categoria_id: int
    class Config:
        from_attributes = True