import os
import shutil
from fastapi import FastAPI, Depends, File, UploadFile, Form, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
import base64
import requests
import pandas as pd
from io import BytesIO
import models, schemas
from typing import List, Optional
from database import engine, get_db

# Seguridad de Tráfico
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Seguridad de Sesión (JWT)
import jwt
from datetime import datetime, timedelta
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

models.Base.metadata.create_all(bind=engine)
app = FastAPI(title="API Surprise Jeans - Fortificada")

# 1. ANTI-DDOS
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# 2. CORS ESTRICTO (Con método PUT habilitado)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://surprise-jeans-catalogo1.vercel.app", 
        "http://localhost:5500", "http://127.0.0.1:5500"
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "PUT"],
    allow_headers=["*"],
)

os.makedirs("static/uploads", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

# ==========================================
# 3. SISTEMA DE LOGIN (JSON Web Tokens)
# ==========================================
SECRET_KEY = "llave_secreta_del_catalogo_surprise"
ALGORITHM = "HS256"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def verificar_token(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("sub") != "admin_yessica":
            raise HTTPException(status_code=401, detail="Pase VIP inválido")
    except:
        raise HTTPException(status_code=401, detail="Token expirado o inválido")

@app.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    if form_data.username == "admin" and form_data.password == "yessica2026":
        expiracion = datetime.utcnow() + timedelta(hours=3)
        token = jwt.encode({"sub": "admin_yessica", "exp": expiracion}, SECRET_KEY, algorithm=ALGORITHM)
        return {"access_token": token, "token_type": "bearer"}
    
    raise HTTPException(status_code=400, detail="Contraseña incorrecta")

@app.get("/")
def inicio():
    return {"mensaje": "Servidor Seguro de Surprise Jeans Operativo 🔒"}

# ==========================================
# 4. RUTAS PÚBLICAS
# ==========================================
@app.get("/categorias", response_model=List[schemas.CategoriaRespuesta])
@limiter.limit("60/minute")
def obtener_categorias(request: Request, db: Session = Depends(get_db)):
    return db.query(models.Categoria).all()

@app.get("/pantalones", response_model=List[schemas.PantalonRespuesta])
@limiter.limit("60/minute")
def obtener_pantalones(
    request: Request,
    skip: int = 0, limit: int = 20, 
    busqueda: Optional[str] = None, categoria_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    query = db.query(models.Pantalon)
    if categoria_id: query = query.filter(models.Pantalon.categoria_id == categoria_id)
    if busqueda: query = query.filter(models.Pantalon.nombre.ilike(f"%{busqueda}%"))
    return query.order_by(models.Pantalon.id.desc()).offset(skip).limit(limit).all()

# ==========================================
# 5. RUTAS ADMINISTRADOR (Exigen Token)
# ==========================================
@app.post("/categorias", response_model=schemas.CategoriaRespuesta)
@limiter.limit("10/minute")
def crear_categoria(
    request: Request, nombre: str = Form(...), 
    db: Session = Depends(get_db), token: str = Depends(verificar_token)
):
    nueva_categoria = models.Categoria(nombre=nombre)
    db.add(nueva_categoria)
    db.commit()
    db.refresh(nueva_categoria)
    return nueva_categoria

@app.delete("/categorias/{categoria_id}")
@limiter.limit("10/minute")
def eliminar_categoria(
    request: Request, categoria_id: int, 
    db: Session = Depends(get_db), token: str = Depends(verificar_token)
):
    categoria = db.query(models.Categoria).filter(models.Categoria.id == categoria_id).first()
    if not categoria: raise HTTPException(status_code=404, detail="Categoría no encontrada")
    
    pantalones_asociados = db.query(models.Pantalon).filter(models.Pantalon.categoria_id == categoria_id).count()
    if pantalones_asociados > 0:
        raise HTTPException(
            status_code=400, 
            detail=f"No puedes borrar esta categoría porque tiene {pantalones_asociados} pantalón(es) asociados. Bórralos o edítalos primero."
        )

    db.delete(categoria)
    db.commit()
    return {"mensaje": "Categoría eliminada"}

@app.post("/pantalones")
@limiter.limit("20/minute")
async def crear_pantalon(
    request: Request, nombre: str = Form(...), precio: float = Form(...),
    stock: int = Form(...), categoria_id: int = Form(...), foto: UploadFile = File(...),
    db: Session = Depends(get_db), token: str = Depends(verificar_token)
):
    contenido = await foto.read()
    imagen_base64 = base64.b64encode(contenido).decode("utf-8")

    API_KEY = "967d4560b8e4d58a4f50db487013722f"
    respuesta = requests.post("https://api.imgbb.com/1/upload", data={"key": API_KEY, "image": imagen_base64})
    
    if respuesta.status_code == 200: url_permanente = respuesta.json()["data"]["url"]
    else: return {"error": "Fallo la subida a ImgBB"}

    nuevo_pantalon = models.Pantalon(nombre=nombre, precio=precio, stock=stock, categoria_id=categoria_id, imagen_url=url_permanente)
    db.add(nuevo_pantalon)
    db.commit()
    return {"mensaje": "Pantalón subido con éxito", "url": url_permanente}

@app.put("/pantalones/{pantalon_id}")
@limiter.limit("20/minute")
async def editar_pantalon(
    request: Request, pantalon_id: int, 
    nombre: str = Form(...), precio: float = Form(...),
    stock: int = Form(...), categoria_id: int = Form(...),
    foto: Optional[UploadFile] = File(None), 
    db: Session = Depends(get_db), token: str = Depends(verificar_token)
):
    pantalon = db.query(models.Pantalon).filter(models.Pantalon.id == pantalon_id).first()
    if not pantalon: return {"error": "Pantalón no encontrado"}
    
    pantalon.nombre = nombre
    pantalon.precio = precio
    pantalon.stock = stock
    pantalon.categoria_id = categoria_id
    
    # Procesamiento de foto opcional
    if foto and foto.filename:
        contenido = await foto.read()
        imagen_base64 = base64.b64encode(contenido).decode("utf-8")
        API_KEY = "967d4560b8e4d58a4f50db487013722f"
        respuesta = requests.post("https://api.imgbb.com/1/upload", data={"key": API_KEY, "image": imagen_base64})
        
        if respuesta.status_code == 200:
            pantalon.imagen_url = respuesta.json()["data"]["url"]
    
    db.commit()
    return {"mensaje": "Pantalón actualizado correctamente"}

@app.delete("/pantalones/{pantalon_id}")
@limiter.limit("15/minute")
def eliminar_pantalon(
    request: Request, pantalon_id: int, 
    db: Session = Depends(get_db), token: str = Depends(verificar_token)
):
    pantalon = db.query(models.Pantalon).filter(models.Pantalon.id == pantalon_id).first()
    if not pantalon: return {"error": "Pantalón no encontrado"}
    db.delete(pantalon)
    db.commit()
    return {"mensaje": "Pantalón eliminado"}

@app.post("/pantalones/excel")
@limiter.limit("5/minute") 
async def subir_excel(
    request: Request, archivo: UploadFile = File(...), 
    db: Session = Depends(get_db), token: str = Depends(verificar_token)
):
    # ¡AHORA ACEPTAMOS .CSV TAMBIÉN!
    if not archivo.filename.endswith(('.xlsx', '.xls', '.csv')):
        return {"error": "El archivo debe ser un Excel (.xlsx, .xls) o CSV (.csv)"}

    contenido = await archivo.read()
    
    try:
        # Detectamos el formato exacto para que pandas lo lea bien
        if archivo.filename.endswith('.csv'):
            df = pd.read_csv(BytesIO(contenido))
        else:
            df = pd.read_excel(BytesIO(contenido))
            
        # Limpiamos los nombres de las columnas por si se coló un espacio en blanco
        df.columns = df.columns.str.strip()
        
        columnas_esperadas = ["Nombre", "Precio", "Stock", "Categoria", "Foto_URL"]
        for col in columnas_esperadas:
            if col not in df.columns:
                return {"error": f"Falta la columna '{col}' en el archivo."}

        pantalones_creados = 0
        for index, fila in df.iterrows():
            nombre_cat = str(fila.get('Categoria', '')).strip()
            
            # Si hay una fila vacía en el Excel, la saltamos
            if not nombre_cat or nombre_cat == 'nan':
                continue
            
            categoria = db.query(models.Categoria).filter(models.Categoria.nombre.ilike(nombre_cat)).first()
            if not categoria:
                categoria = models.Categoria(nombre=nombre_cat)
                db.add(categoria)
                db.commit()
                db.refresh(categoria)
            
            foto_url = str(fila.get('Foto_URL', ''))
            if foto_url == 'nan' or not foto_url.startswith('http'):
                foto_url = "https://dummyimage.com/400x500/e0e7ff/3730a3&text=FOTO+PENDIENTE"

            nuevo_pantalon = models.Pantalon(
                nombre=str(fila['Nombre']).strip(), precio=float(fila['Precio']),
                stock=int(fila['Stock']), categoria_id=categoria.id, imagen_url=foto_url
            )
            db.add(nuevo_pantalon)
            pantalones_creados += 1
            
        db.commit()
        return {"mensaje": f"Carga masiva exitosa. Se crearon {pantalones_creados} modelos."}
        
    except Exception as e:
        print("Error leyendo archivo:", e)
        return {"error": "Hubo un problema al leer los datos. Verifica el formato del archivo."}