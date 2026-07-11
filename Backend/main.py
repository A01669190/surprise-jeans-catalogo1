import os
import shutil
from fastapi import FastAPI, Depends, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
import base64
import requests
import models, schemas
from typing import List, Optional
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
def obtener_pantalones(
    skip: int = 0, 
    limit: int = 20, 
    busqueda: Optional[str] = None,
    categoria_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    query = db.query(models.Pantalon)
    
    # Filtro por categoría
    if categoria_id:
        query = query.filter(models.Pantalon.categoria_id == categoria_id)
        
    # Filtro del buscador de texto
    if busqueda:
        query = query.filter(models.Pantalon.nombre.ilike(f"%{busqueda}%"))
        
    # Ordenamos para que los modelos más nuevos salgan primero
    query = query.order_by(models.Pantalon.id.desc())
        
    # Aplicamos la paginación (Limit y Offset)
    return query.offset(skip).limit(limit).all()

@app.post("/pantalones")
async def crear_pantalon(
    nombre: str = Form(...),
    precio: float = Form(...),
    stock: int = Form(...), # <--- Guardamos la cantidad
    categoria_id: int = Form(...),
    foto: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    contenido = await foto.read()
    imagen_base64 = base64.b64encode(contenido).decode("utf-8")

    API_KEY = "967d4560b8e4d58a4f50db487013722f"
    url_imgbb = "https://api.imgbb.com/1/upload"
    payload = {"key": API_KEY, "image": imagen_base64}
    
    respuesta = requests.post(url_imgbb, data=payload)
    datos = respuesta.json()

    if respuesta.status_code == 200:
        url_permanente = datos["data"]["url"]
    else:
        return {"error": "Fallo la subida de la imagen a la nube."}

    nuevo_pantalon = models.Pantalon(
        nombre=nombre,
        precio=precio,
        stock=stock,
        categoria_id=categoria_id,
        imagen_url=url_permanente
    )
    db.add(nuevo_pantalon)
    db.commit()

    return {"mensaje": "Pantalón subido con éxito", "url": url_permanente}

# --- NUEVA RUTA: ELIMINAR ---
@app.delete("/pantalones/{pantalon_id}")
def eliminar_pantalon(pantalon_id: int, db: Session = Depends(get_db)):
    pantalon = db.query(models.Pantalon).filter(models.Pantalon.id == pantalon_id).first()
    if not pantalon:
        return {"error": "Pantalón no encontrado"}
    db.delete(pantalon)
    db.commit()
    return {"mensaje": "Pantalón eliminado"}

# --- RUTA DE REINICIO ---
@app.get("/reset-db-total")
def reset_db_total():
    models.Base.metadata.drop_all(bind=engine)
    models.Base.metadata.create_all(bind=engine)
    return {"mensaje": "Tablas formateadas exitosamente."}