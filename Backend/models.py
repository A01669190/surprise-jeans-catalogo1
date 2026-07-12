from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime
from sqlalchemy.orm import relationship
import datetime
from database import Base

class Categoria(Base):
    __tablename__ = "categorias"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, unique=True, index=True)
    pantalones = relationship("Pantalon", back_populates="categoria")

class Pantalon(Base):
    __tablename__ = "pantalones"
    id = Column(Integer, primary_key=True, index=True)
    codigo = Column(String, index=True)
    nombre = Column(String, index=True)
    descripcion = Column(String, nullable=True)
    precio = Column(Float)
    stock = Column(Integer, default=0)
    imagen_url = Column(String)
    categoria_id = Column(Integer, ForeignKey("categorias.id"))
    categoria = relationship("Categoria", back_populates="pantalones")

# ==========================================
# TABLAS DE SEGURIDAD (PEDIDOS)
## ==========================================
# TABLAS DE SEGURIDAD (PEDIDOS)
# ==========================================
class Pedido(Base):
    __tablename__ = "pedidos"
    id = Column(Integer, primary_key=True, index=True)
    nombre_cliente = Column(String)
    telefono = Column(String)
    calle_numero = Column(String)
    colonia = Column(String)
    ciudad = Column(String)
    estado = Column(String)
    codigo_postal = Column(String)
    referencias = Column(String, nullable=True)
    total = Column(Float)
    estatus = Column(String, default="PENDIENTE")
    fecha = Column(DateTime, default=datetime.datetime.utcnow)
    detalles = relationship("DetallePedido", back_populates="pedido")

class DetallePedido(Base):
    __tablename__ = "detalles_pedido"
    id = Column(Integer, primary_key=True, index=True)
    pedido_id = Column(Integer, ForeignKey("pedidos.id"))
    pantalon_id = Column(Integer, ForeignKey("pantalones.id"))
    cantidad = Column(Integer)
    precio_unitario = Column(Float)
    pedido = relationship("Pedido", back_populates="detalles")