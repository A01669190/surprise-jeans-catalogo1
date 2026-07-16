from pydantic import BaseModel
from typing import Optional, List

class CategoriaBase(BaseModel):
    nombre: str

class CategoriaRespuesta(CategoriaBase):
    id: int
    class Config:
        from_attributes = True

class VarianteResponse(BaseModel):
    talla: str
    stock: int
    sku: str

    class Config:
        from_attributes = True  # Usa orm_mode = True si usas Pydantic v1

class PantalonRespuesta(BaseModel):
    id: int
    codigo: str  
    nombre: str
    descripcion: Optional[str] = None
    precio: float
    tallas: List[VarianteResponse] = []
    imagen_url: str
    categoria_id: int
    stock: int
    promedio_estrellas: float = 0.0  # ⚡ NUEVO
    total_resenas: int = 0          # ⚡ NUEVO
    class Config:
        from_attributes = True

# ⚡ NUEVO: ESQUEMA DE RESEÑAS
class ResenaCrear(BaseModel):
    calificacion: int
    comentario: Optional[str] = None

# ==========================================
# ESQUEMAS PARA LA BÓVEDA FINANCIERA Y CLIENTES (Sin cambios)
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
    cupon: Optional[str] = None
    usar_puntos: Optional[bool] = False

class ValidarCuponReq(BaseModel):
    codigo: str

class ClienteRegistro(BaseModel):
    nombre_completo: str
    correo: str
    password: str
    telefono: str

class CambioPasswordReq(BaseModel):
    password_actual: str
    password_nueva: str

class PantalonUpdateRapido(BaseModel):
    precio: Optional[float] = None
    stock: Optional[int] = None

