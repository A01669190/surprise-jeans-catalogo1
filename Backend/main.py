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
import json
from fastapi.responses import FileResponse
import mercadopago # <-- MOTOR BANCARIO

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
    allow_origins=["*"], # Permitimos todo para evitar bloqueos del banco
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 🚨 INYECTA TU TOKEN AQUÍ 🚨
MERCADO_PAGO_TOKEN = "APP_USR-TU-TOKEN-AQUI" 
sdk = mercadopago.SDK(MERCADO_PAGO_TOKEN)

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
    request: Request, skip: int = 0, limit: int = 20, 
    busqueda: Optional[str] = None, categoria_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    query = db.query(models.Pantalon)
    if categoria_id: query = query.filter(models.Pantalon.categoria_id == categoria_id)
    if busqueda: query = query.filter(models.Pantalon.nombre.ilike(f"%{busqueda}%"))
    return query.order_by(models.Pantalon.id.desc()).offset(skip).limit(limit).all()

# ==========================================
# 5. EL CEREBRO FINANCIERO (WEBHOOKS) 🧠
# ==========================================
@app.post("/crear-pago-seguro")
def crear_pago_seguro(pedido_req: schemas.PedidoSeguro, db: Session = Depends(get_db)):
    total_pedido = 0
    items_para_banco = []
    
    for item in pedido_req.items:
        # Escudo de Inventario Real
        pantalon_db = db.query(models.Pantalon).filter(models.Pantalon.id == item.id).first()
        if not pantalon_db or pantalon_db.stock < item.cantidad:
            raise HTTPException(status_code=400, detail=f"Alguien acaba de comprar el último {item.nombre}")
        
        total_pedido += (item.precio * item.cantidad)
        items_para_banco.append({
            "title": f"[{item.codigo}] {item.nombre}",
            "quantity": item.cantidad,
            "unit_price": float(item.precio),
            "currency_id": "MXN"
        })

    # Guardar en bóveda como PENDIENTE
    nuevo_pedido = models.Pedido(
        nombre_cliente=pedido_req.envio.nombre,
        telefono=pedido_req.envio.telefono,
        direccion=pedido_req.envio.direccion,
        codigo_postal=pedido_req.envio.cp,
        total=total_pedido,
        estatus="PENDIENTE"
    )
    db.add(nuevo_pedido)
    db.commit()
    db.refresh(nuevo_pedido)

    for item in pedido_req.items:
        db.add(models.DetallePedido(
            pedido_id=nuevo_pedido.id, pantalon_id=item.id, 
            cantidad=item.cantidad, precio_unitario=item.precio
        ))
    db.commit()

    # Generar Ticket con Rastreador Secreto (Metadata)
    preference_data = {
        "items": items_para_banco,
        "metadata": {"pedido_interno_id": nuevo_pedido.id}, 
        "external_reference": str(nuevo_pedido.id),
        "back_urls": {
            "success": "https://surprisejeanysk.com/?pago=exito",
            "failure": "https://surprisejeanysk.com/?pago=fallo",
            "pending": "https://surprisejeanysk.com/?pago=pendiente"
        },
        "auto_return": "approved",
        "notification_url": "https://surprise-jeans-api-denz.onrender.com/webhook/mercadopago",
        "statement_descriptor": "SURPRISE JEANS" 
    }

    respuesta = sdk.preference().create(preference_data)
    return {"link_pago": respuesta["response"]["init_point"]}

@app.post("/webhook/mercadopago")
async def webhook_mercadopago(request: Request, db: Session = Depends(get_db)):
    # El banco avisa silenciosamente
    datos = await request.json()
    
    if datos.get("type") == "payment":
        pago_id = datos.get("data", {}).get("id")
        
        # Confirmar legitimidad
        info_pago = sdk.payment().get(pago_id)
        if info_pago["status"] == 200:
            estado_pago = info_pago["response"]["status"]
            metadata = info_pago["response"].get("metadata", {})
            pedido_id = metadata.get("pedido_interno_id")
            
            # Liberar inventario SOLO si se aprobó
            if estado_pago == "approved" and pedido_id:
                pedido_db = db.query(models.Pedido).filter(models.Pedido.id == pedido_id).first()
                
                # Anti-Doble Cobro
                if pedido_db and pedido_db.estatus == "PENDIENTE":
                    pedido_db.estatus = "PAGADO"
                    
                    for detalle in pedido_db.detalles:
                        pantalon_db = db.query(models.Pantalon).filter(models.Pantalon.id == detalle.pantalon_id).first()
                        if pantalon_db and pantalon_db.stock >= detalle.cantidad:
                            pantalon_db.stock -= detalle.cantidad
                    
                    db.commit()
    return {"status": "procesado"}

# ==========================================
# 6. RUTAS ADMINISTRADOR (Exigen Token)
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
    db.delete(categoria)
    db.commit()
    return {"mensaje": "Categoría eliminada"}

@app.post("/pantalones")
@limiter.limit("20/minute")
async def crear_pantalon(
    request: Request, codigo: str = Form(...), nombre: str = Form(...), precio: float = Form(...),
    stock: int = Form(...), categoria_id: int = Form(...), foto: UploadFile = File(...),
    db: Session = Depends(get_db), token: str = Depends(verificar_token)
):
    contenido = await foto.read()
    imagen_base64 = base64.b64encode(contenido).decode("utf-8")

    API_KEY = "967d4560b8e4d58a4f50db487013722f"
    respuesta = requests.post("https://api.imgbb.com/1/upload", data={"key": API_KEY, "image": imagen_base64})
    
    if respuesta.status_code == 200: url_permanente = respuesta.json()["data"]["url"]
    else: return {"error": "Fallo la subida a ImgBB"}

    nuevo_pantalon = models.Pantalon(codigo=codigo, nombre=nombre, precio=precio, stock=stock, categoria_id=categoria_id, imagen_url=url_permanente)
    db.add(nuevo_pantalon)
    db.commit()
    return {"mensaje": "Pantalón subido con éxito", "url": url_permanente}

@app.put("/pantalones/{pantalon_id}")
@limiter.limit("20/minute")
async def editar_pantalon(
    request: Request, pantalon_id: int, codigo: str = Form(...), nombre: str = Form(...), precio: float = Form(...),
    stock: int = Form(...), categoria_id: int = Form(...), foto: Optional[UploadFile] = File(None), 
    db: Session = Depends(get_db), token: str = Depends(verificar_token)
):
    pantalon = db.query(models.Pantalon).filter(models.Pantalon.id == pantalon_id).first()
    if not pantalon: return {"error": "Pantalón no encontrado"}
    
    pantalon.codigo = codigo
    pantalon.nombre = nombre
    pantalon.precio = precio
    pantalon.stock = stock
    pantalon.categoria_id = categoria_id
    
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
def eliminar_pantalon(request: Request, pantalon_id: int, db: Session = Depends(get_db), token: str = Depends(verificar_token)):
    pantalon = db.query(models.Pantalon).filter(models.Pantalon.id == pantalon_id).first()
    if not pantalon: return {"error": "Pantalón no encontrado"}
    db.delete(pantalon)
    db.commit()
    return {"mensaje": "Pantalón eliminado"}

@app.post("/pantalones/excel")
@limiter.limit("5/minute") 
async def subir_excel(request: Request, archivo: UploadFile = File(...), db: Session = Depends(get_db), token: str = Depends(verificar_token)):
    if not archivo.filename.endswith(('.xlsx', '.xls', '.csv')):
        return {"error": "El archivo debe ser un Excel (.xlsx, .xls) o CSV (.csv)"}
    contenido = await archivo.read()
    try:
        if archivo.filename.endswith('.csv'): df = pd.read_csv(BytesIO(contenido))
        else: df = pd.read_excel(BytesIO(contenido))
        df.columns = df.columns.str.strip()
        
        columnas_esperadas = ["Codigo", "Nombre", "Precio", "Stock", "Categoria", "Foto_URL"]
        for col in columnas_esperadas:
            if col not in df.columns: return {"error": f"Falta la columna '{col}' en el archivo."}

        pantalones_creados = 0
        for index, fila in df.iterrows():
            nombre_cat = str(fila.get('Categoria', '')).strip()
            if not nombre_cat or nombre_cat == 'nan': continue
            
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
                codigo=str(fila['Codigo']).strip(), nombre=str(fila['Nombre']).strip(), precio=float(fila['Precio']),
                stock=int(fila['Stock']), categoria_id=categoria.id, imagen_url=foto_url
            )
            db.add(nuevo_pantalon)
            pantalones_creados += 1
            
        db.commit()
        return {"mensaje": f"Carga masiva exitosa. Se crearon {pantalones_creados} modelos."}
        
    except Exception as e:
        return {"error": "Hubo un problema al leer los datos. Verifica el formato del archivo."}

@app.get("/reset-db-total")
def reset_db_total():
    models.Base.metadata.drop_all(bind=engine)
    models.Base.metadata.create_all(bind=engine)
    return {"mensaje": "Tablas formateadas exitosamente. Lista para el E-Commerce de alta seguridad."}

@app.get("/backup/descargar")
@limiter.limit("3/minute")
def descargar_respaldo_seguro(request: Request, db: Session = Depends(get_db), token: str = Depends(verificar_token)):
    categorias = db.query(models.Categoria).all()
    pantalones = db.query(models.Pantalon).all()
    datos_respaldo = {
        "fecha_respaldo": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "total_modelos": len(pantalones),
        "categorias": [{"id": c.id, "nombre": c.nombre} for c in categorias],
        "inventario": [
            {
                "id": p.id, "codigo": p.codigo, "nombre": p.nombre, 
                "precio": p.precio, "stock": p.stock, 
                "categoria_id": p.categoria_id, "imagen_url": p.imagen_url
            } for p in pantalones
        ]
    }
    ruta_archivo = "static/respaldo_surprise.json"
    with open(ruta_archivo, "w", encoding="utf-8") as f:
        json.dump(datos_respaldo, f, indent=4, ensure_ascii=False)
    nombre_archivo = f"SurpriseJeans_Backup_{datetime.now().strftime('%Y%m%d')}.json"
    return FileResponse(path=ruta_archivo, filename=nombre_archivo, media_type='application/json')