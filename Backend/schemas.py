from pydantic import BaseModel
from typing import Optional, List

class CategoriaBase(BaseModel):
    nombre: str

class CategoriaRespuesta(CategoriaBase):
    id: int
    class Config:
        from_attributes = True

class PantalonRespuesta(BaseModel):
    id: int
    codigo: str  
    nombre: str
    descripcion: Optional[str] = None
    precio: float
    imagen_url: str
    categoria_id: int
    stock: int
    class Config:
        from_attributes = True

# ==========================================
# ESQUEMAS PARA LA BÓVEDA FINANCIERA
# ==========================================
class ItemCarrito(BaseModel):
    id: int
    nombre: str
    precio: float
    cantidad: int
    codigo: str

class InfoEnvio(BaseModel):
    nombre: str
    telefono: str
    calle_numero: str
    colonia: str
    ciudad: str
    estado: str
    cp: str
    referencias: Optional[str] = None

class PedidoSeguro(BaseModel):
    envio: InfoEnvio
    items: List[ItemCarrito]