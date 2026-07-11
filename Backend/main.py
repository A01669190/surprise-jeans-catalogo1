import os
import shutil
from fastapi import FastAPI, Depends, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from typing import List

import models, schemas
from database import engine, get_db

# Crea las tablas si no existen
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="API Surprise Jeans")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 1. Crear carpeta para guardar fotos y hacerla pública
os.makedirs("static/uploads", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def inicio():
    return {"mensaje": "¡El servidor de Surprise Jeans está vivo! 🚀"}

# --- RUTAS DE CATEGORÍAS ---

@app.get("/categorias", response_model=List[schemas.CategoriaRespuesta])
def obtener_categorias(db: Session = Depends(get_db)):
    return db.query(models.Categoria).all()

@app.post("/categorias", response_model=schemas.CategoriaRespuesta)
def crear_categoria(nombre: str = Form(...), db: Session = Depends(get_db)):
    nueva_categoria = models.Categoria(nombre=nombre)
    db.add(nueva_categoria)
    db.commit()
    db.refresh(nueva_categoria)
    return nueva_categoria

# --- RUTAS DE PANTALONES ---

@app.get("/pantalones", response_model=List[schemas.PantalonRespuesta])
def obtener_pantalones(db: Session = Depends(get_db)):
    return db.query(models.Pantalon).all()

@app.post("/pantalones", response_model=schemas.PantalonRespuesta)
def crear_pantalon(
    nombre: str = Form(...),
    descripcion: str = Form(None),
    precio: float = Form(...),
    categoria_id: int = Form(...),
    foto: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    # Guardar la foto en la carpeta local
    ruta_foto = f"static/uploads/{foto.filename}"
    with open(ruta_foto, "wb") as buffer:
        shutil.copyfileobj(foto.file, buffer)
    
    # Generar el enlace público y guardar en base de datos
    url_publica = f"http://localhost:8000/{ruta_foto}"
    nuevo_pantalon = models.Pantalon(
        nombre=nombre,
        descripcion=descripcion,
        precio=precio,
        categoria_id=categoria_id,
        imagen_url=url_publica
    )
    
    db.add(nuevo_pantalon)
    db.commit()
    db.refresh(nuevo_pantalon)
    return nuevo_pantalon