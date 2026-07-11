import os
import shutil
from fastapi import FastAPI, Depends, File, UploadFile, Form, Request # <-- Agregamos Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
import base64
import requests
import models, schemas
from typing import List, Optional
from database import engine, get_db

# --- NUEVAS LIBRERÍAS DE SEGURIDAD (WAF) ---
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Crea las tablas si no existen
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="API Surprise Jeans - Secure")

# 1. CONFIGURACIÓN DE MITIGACIÓN DE TRÁFICO (Anti-DDoS)
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# 2. LISTA DE CONTROL DE ACCESO (CORS Estricto)
# Ya no aceptamos "*". Solo tu página oficial y tu Mac pueden hablar con la base de datos.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://surprise-jeans-catalogo1.vercel.app", 
        "http://localhost:5500",
        "http://127.0.0.1:5500"
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"], # Bloqueamos métodos no autorizados
    allow_headers=["*"],
)

os.makedirs("static/uploads", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def inicio():
    return {"mensaje": "Servidor Seguro de Surprise Jeans Operativo 🔒"}

# --- RUTAS PÚBLICAS (Límites generosos) ---
@app.get("/categorias", response_model=List[schemas.CategoriaRespuesta])
@limiter.limit("60/minute") # Máximo 60 recargas por minuto por usuario
def obtener_categorias(request: Request, db: Session = Depends(get_db)):
    return db.query(models.Categoria).all()

@app.get("/pantalones", response_model=List[schemas.PantalonRespuesta])
@limiter.limit("60/minute")
def obtener_pantalones(
    request: Request,
    skip: int = 0, 
    limit: int = 20, 
    busqueda: Optional[str] = None,
    categoria_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    query = db.query(models.Pantalon)
    if categoria_id:
        query = query.filter(models.Pantalon.categoria_id == categoria_id)
    if busqueda:
        query = query.filter(models.Pantalon.nombre.ilike(f"%{busqueda}%"))
    query = query.order_by(models.Pantalon.id.desc())
    return query.offset(skip).limit(limit).all()

# --- RUTAS ADMINISTRATIVAS (Límites estrictos de seguridad) ---
@app.post("/categorias", response_model=schemas.CategoriaRespuesta)
@limiter.limit("10/minute") # Solo permitimos crear 10 categorías por minuto
def crear_categoria(request: Request, nombre: str = Form(...), db: Session = Depends(get_db)):
    nueva_categoria = models.Categoria(nombre=nombre)
    db.add(nueva_categoria)
    db.commit()
    db.refresh(nueva_categoria)
    return nueva_categoria

@app.post("/pantalones")
@limiter.limit("20/minute") # Evita que un bot sature la subida de imágenes a ImgBB
async def crear_pantalon(
    request: Request,
    nombre: str = Form(...),
    precio: float = Form(...),
    stock: int = Form(...),
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

@app.delete("/pantalones/{pantalon_id}")
@limiter.limit("15/minute") # Evita que borren toda la base de datos de golpe
def eliminar_pantalon(request: Request, pantalon_id: int, db: Session = Depends(get_db)):
    pantalon = db.query(models.Pantalon).filter(models.Pantalon.id == pantalon_id).first()
    if not pantalon:
        return {"error": "Pantalón no encontrado"}
    db.delete(pantalon)
    db.commit()
    return {"mensaje": "Pantalón eliminado"}

@app.get("/reset-db-total")
def reset_db_total():
    models.Base.metadata.drop_all(bind=engine)
    models.Base.metadata.create_all(bind=engine)
    return {"mensaje": "Tablas formateadas exitosamente."}