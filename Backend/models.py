from sqlalchemy import Column, Integer, String, Float, ForeignKey
from sqlalchemy.orm import relationship
from database import Base

class Categoria(Base):
    __tablename__ = "categorias"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, unique=True, index=True)
    
    # Relación para saber qué pantalones pertenecen a esta categoría
    pantalones = relationship("Pantalon", back_populates="categoria")

class Pantalon(Base):
    __tablename__ = "pantalones"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, index=True)
    descripcion = Column(String, nullable=True)
    precio = Column(Float)
    imagen_url = Column(String) # Aquí guardaremos la ruta de la foto
    categoria_id = Column(Integer, ForeignKey("categorias.id"))
    
    categoria = relationship("Categoria", back_populates="pantalones")