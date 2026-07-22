from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime
from sqlalchemy.orm import relationship, object_session
from sqlalchemy import func
from datetime import datetime, timezone
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
    resenas = relationship("Resena", back_populates="pantalon", cascade="all, delete-orphan")
    detalles = relationship("DetallePedido", back_populates="pantalon")

    # ⚡ CALCULADORA OPTIMIZADA POR BASE DE DATOS (N+1 FIXED)
    @property
    def promedio_estrellas(self):
        session = object_session(self)
        if session:
            resultado = session.query(func.avg(Resena.calificacion)).filter(Resena.pantalon_id == self.id, Resena.calificacion >= 3).scalar()
            return float(resultado) if resultado else 0.0
        return 0.0

    @property
    def total_resenas(self):
        session = object_session(self)
        if session:
            return session.query(func.count(Resena.id)).filter(Resena.pantalon_id == self.id, Resena.calificacion >= 3).scalar() or 0
        return 0
    tallas = relationship("VarianteTalla", back_populates="pantalon", cascade="all, delete-orphan")

class VarianteTalla(Base):
    __tablename__ = "variantes_talla"
    id = Column(Integer, primary_key=True, index=True)
    pantalon_id = Column(Integer, ForeignKey("pantalones.id", ondelete="CASCADE"))
    talla = Column(String)  
    color = Column(String, default="Original") # ⚡ NUEVA COLUMNA PARA COLORES
    stock = Column(Integer, default=0)
    sku = Column(String, unique=True, index=True) 
    pantalon = relationship("Pantalon", back_populates="tallas")

class Resena(Base):
    __tablename__ = "resenas"
    id = Column(Integer, primary_key=True, index=True)
    pantalon_id = Column(Integer, ForeignKey("pantalones.id"))
    cliente_id = Column(Integer, ForeignKey("clientes.id"))
    calificacion = Column(Integer) # Del 1 al 5
    comentario = Column(String, nullable=True)

    fecha = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    fecha_registro = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    pantalon = relationship("Pantalon", back_populates="resenas")
    cliente = relationship("Cliente")

# ==========================================
# TABLAS DE SEGURIDAD (PEDIDOS)
class Pedido(Base):
    __tablename__ = "pedidos"
    id = Column(Integer, primary_key=True, index=True)
    correo_cliente = Column(String, index=True, nullable=True)
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
    guia_rastreo = Column(String, nullable=True) 
    pago_id = Column(String, nullable=True) # ⚡ NUEVA COLUMNA PARA REEMBOLSOS
    fecha = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    detalles = relationship("DetallePedido", back_populates="pedido", cascade="all, delete-orphan")

class DetallePedido(Base):
    __tablename__ = "detalles_pedido"
    id = Column(Integer, primary_key=True, index=True)
    pedido_id = Column(Integer, ForeignKey("pedidos.id"))
    pantalon_id = Column(Integer, ForeignKey("pantalones.id"))
    cantidad = Column(Integer)
    precio_unitario = Column(Float)
    sku_variante = Column(String, nullable=True) # ⚡ NUEVO: Guarda el SKU exacto
    talla = Column(String, nullable=True)        # ⚡ NUEVO: Guarda la talla

    pedido = relationship("Pedido", back_populates="detalles")
    pantalon = relationship("Pantalon")

# ==========================================
# TABLA DE CLIENTES Y CUPONES (Sin cambios)
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
    puntos = Column(Float, default=0.0)
    fecha_registro = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class Cupon(Base):
    __tablename__ = "cupones"
    id = Column(Integer, primary_key=True, index=True)
    codigo = Column(String, unique=True, index=True)
    porcentaje = Column(Float)
    activo = Column(Integer, default=1)