import os
import shutil
from fastapi import FastAPI, Depends, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from typing import List
import base64
import requests
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
# CORRECCIÓN: Render ya está en la carpeta Backend, así que solo buscamos "static"
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

@app.post("/pantalones")
async def crear_pantalon(
    nombre: str = Form(...),
    precio: float = Form(...),
    categoria_id: int = Form(...),
    foto: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    # 1. Leer imagen y convertir a Base64 para enviarla por red
    contenido = await foto.read()
    imagen_base64 = base64.b64encode(contenido).decode("utf-8")

    # 2. Configurar la petición a la API de ImgBB
    API_KEY = "967d4560b8e4d58a4f50db487013722f" # <--- ¡Pon tu llave de ImgBB aquí!
    url_imgbb = "https://api.imgbb.com/1/upload"
    payload = {
        "key": API_KEY,
        "image": imagen_base64
    }

    # 3. Enviar el HTTP POST
    respuesta = requests.post(url_imgbb, data=payload)
    datos = respuesta.json()

    # Si todo salió bien, ImgBB nos regresa el link final de la foto en la nube
    if respuesta.status_code == 200:
        url_permanente = datos["data"]["url"]
    else:
        return {"error": "Fallo la subida de la imagen a la nube."}

    # 4. Guardar los datos en PostgreSQL
    nuevo_pantalon = models.Pantalon(
        nombre=nombre,
        precio=precio,
        categoria_id=categoria_id,
        imagen_url=url_permanente
    )
    db.add(nuevo_pantalon)
    db.commit()

    return {"mensaje": "Pantalón subido con éxito", "url": url_permanente}