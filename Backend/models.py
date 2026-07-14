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

# ==========================================
# TABLA DE CLIENTES (USUARIOS REGISTRADOS)
class Cliente(Base):
    __tablename__ = "clientes"
    id = Column(Integer, primary_key=True, index=True)
    nombre_completo = Column(String)
    correo = Column(String, unique=True, index=True)
    password_hash = Column(String)
    telefono = Column(String, nullable=True)
    
    calle_numero = Column(String, nullable=True)
    colonia = Column(String, nullable=True)
    ciudad = Column(String, nullable=True)
    estado = Column(String, nullable=True)
    codigo_postal = Column(String, nullable=True)
    referencias_domicilio = Column(String, nullable=True)
    
    puntos = Column(Float, default=0.0) # Bóveda de Surprise Points
    
    fecha_registro = Column(DateTime, default=datetime.datetime.utcnow)

# ==========================================
# TABLA DE CUPONES DE DESCUENTO
class Cupon(Base):
    __tablename__ = "cupones"
    id = Column(Integer, primary_key=True, index=True)
    codigo = Column(String, unique=True, index=True)
    porcentaje = Column(Float)
    activo = Column(Integer, default=1)