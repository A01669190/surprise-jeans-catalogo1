import os
import shutil
from fastapi import FastAPI, Depends, File, UploadFile, Form, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
import base64
import requests
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

# 2. CORS ESTRICTO
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://surprise-jeans-catalogo1.vercel.app", 
        "http://localhost:5500", "http://127.0.0.1:5500"
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
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
    # Aquí escondemos la contraseña real en el servidor
    if form_data.username == "admin" and form_data.password == "yessica2026":
        expiracion = datetime.utcnow() + timedelta(hours=3) # El token dura 3 horas
        token = jwt.encode({"sub": "admin_yessica", "exp": expiracion}, SECRET_KEY, algorithm=ALGORITHM)
        return {"access_token": token, "token_type": "bearer"}
    
    raise HTTPException(status_code=400, detail="Contraseña incorrecta")

@app.get("/")
def inicio():
    return {"mensaje": "Servidor Seguro de Surprise Jeans Operativo 🔒"}

# ==========================================
# 4. RUTAS PÚBLICAS (No requieren Token)
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
# 5. RUTAS ADMINISTRADOR (Exigen Token JWT)
# ==========================================
@app.post("/categorias", response_model=schemas.CategoriaRespuesta)
@limiter.limit("10/minute")
def crear_categoria(
    request: Request, nombre: str = Form(...), 
    db: Session = Depends(get_db), token: str = Depends(verificar_token) # <-- Candado
):
    nueva_categoria = models.Categoria(nombre=nombre)
    db.add(nueva_categoria)
    db.commit()
    db.refresh(nueva_categoria)
    return nueva_categoria

@app.post("/pantalones")
@limiter.limit("20/minute")
async def crear_pantalon(
    request: Request, nombre: str = Form(...), precio: float = Form(...),
    stock: int = Form(...), categoria_id: int = Form(...), foto: UploadFile = File(...),
    db: Session = Depends(get_db), token: str = Depends(verificar_token) # <-- Candado
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

@app.delete("/pantalones/{pantalon_id}")
@limiter.limit("15/minute")
def eliminar_pantalon(
    request: Request, pantalon_id: int, 
    db: Session = Depends(get_db), token: str = Depends(verificar_token) # <-- Candado
):
    pantalon = db.query(models.Pantalon).filter(models.Pantalon.id == pantalon_id).first()
    if not pantalon: return {"error": "Pantalón no encontrado"}
    db.delete(pantalon)
    db.commit()
    return {"mensaje": "Pantalón eliminado"}

@app.get("/reset-db-total")
def reset_db_total():
    models.Base.metadata.drop_all(bind=engine)
    models.Base.metadata.create_all(bind=engine)
    return {"mensaje": "Tablas formateadas exitosamente."}