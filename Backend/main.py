import os
import shutil
from fastapi import FastAPI, Depends, File, UploadFile, Form, Request, HTTPException, status, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session  # <--- ¡ESTA ES LA LÍNEA QUE FALTABA!
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
from sqlalchemy import text
import bcrypt
# Seguridad de Tráfico
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import string
import random
from pydantic import BaseModel
# Seguridad de Sesión (JWT)
import jwt
from datetime import datetime, timedelta
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi import WebSocket, WebSocketDisconnect

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
MERCADO_PAGO_TOKEN = "APP_USR-6792882002477550-071212-6f1803d40518512e66004fa3f88bf870-3538372902" 
sdk = mercadopago.SDK(MERCADO_PAGO_TOKEN)

os.makedirs("static/uploads", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

# ==========================================
# 3. SISTEMA DE LOGIN (JSON Web Tokens)
# ==========================================
SECRET_KEY = os.getenv("JWT_SECRET", "llave_secreta_del_catalogo_surprise")
# ==========================================
# VARIABLES DE ENTORNO (SEGURIDAD)
# ==========================================
import os
SECRET_KEY = os.getenv("JWT_SECRET", "llave_secreta_del_catalogo_surprise")
GMAIL_USER = os.getenv("GMAIL_USER", "denzellopezcabrera@gmail.com")
GMAIL_PASSWORD = os.getenv("GMAIL_PASSWORD", "")
ALGORITHM = "HS256"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

# ==========================================
# INFRAESTRUCTURA DE WEBSOCKETS (TIEMPO REAL)
# ==========================================
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except:
                pass

manager = ConnectionManager()

@app.websocket("/ws/despacho")
async def websocket_despacho(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# ==========================================
# MOTOR CRIPTOGRÁFICO (PURO BCRYPT - SIN BUGS)
# ==========================================
def obtener_hash_password(password: str):
    # Convertimos la contraseña a bytes y le aplicamos sal (seguridad extra)
    pwd_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(pwd_bytes, salt)
    return hashed_password.decode('utf-8')

def verificar_password(plain_password: str, hashed_password: str):
    # Comparamos la contraseña limpia con el código de la bóveda
    password_byte_enc = plain_password.encode('utf-8')
    hashed_password_bytes = hashed_password.encode('utf-8')
    return bcrypt.checkpw(password_byte_enc, hashed_password_bytes)

# ==========================================
# SISTEMA DE CLIENTES (REGISTRO Y LOGIN)
# ==========================================
@app.post("/registro")
def registrar_cliente(cliente: schemas.ClienteRegistro, db: Session = Depends(get_db)):
    # 1. Verificación
    db_cliente = db.query(models.Cliente).filter(models.Cliente.correo == cliente.correo).first()
    if db_cliente:
        raise HTTPException(status_code=400, detail="Este correo ya está registrado.")
    
    # 2. Encriptación
    password_encriptada = obtener_hash_password(cliente.password)
    
    # 3. Guardado en Bóveda
    nuevo_cliente = models.Cliente(
        nombre_completo=cliente.nombre_completo,
        correo=cliente.correo,
        password_hash=password_encriptada,
        telefono=cliente.telefono
    )
    db.add(nuevo_cliente)
    db.commit()

    # NOTA: Motor de correo desactivado para evitar el bloqueo del puerto 587 en Render Gratuito.
    return {"mensaje": "Cuenta creada con éxito."}

@app.post("/login-cliente")
def login_cliente(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # Usamos form_data.username para recibir el correo del cliente
    cliente = db.query(models.Cliente).filter(models.Cliente.correo == form_data.username).first()
    
    # Verificamos que el cliente exista y que la contraseña coincida con el hash
    if not cliente or not verificar_password(form_data.password, cliente.password_hash):
        raise HTTPException(status_code=401, detail="Correo o contraseña incorrectos.")
    
    # Generamos su Pase VIP (JWT)
    token_data = {"sub": cliente.correo, "rol": "cliente", "id": cliente.id}
    token = jwt.encode(token_data, SECRET_KEY, algorithm=ALGORITHM)
    
    return {
        "access_token": token, 
        "token_type": "bearer", 
        "nombre": cliente.nombre_completo
    }

def verificar_token(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("sub") != "admin_yessica":
            raise HTTPException(status_code=401, detail="Pase VIP inválido")
    except:
        raise HTTPException(status_code=401, detail="Token expirado o inválido")
    
def verificar_token_cliente(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("rol") != "cliente":
            raise HTTPException(status_code=401, detail="Token no válido para cliente")
        return payload.get("sub") # Devuelve el correo del cliente
    except:
        raise HTTPException(status_code=401, detail="Token expirado o inválido")


@app.post("/recuperar-password")
async def recuperar_password(request: Request, db: Session = Depends(get_db)):
    data = await request.json()
    correo = data.get("correo")
    cliente = db.query(models.Cliente).filter(models.Cliente.correo == correo).first()
    
    # Seguridad anti-rastreo
    if not cliente:
        return {"mensaje": "Proceso completado.", "nueva_pass": None}
    
    # 1. Generamos contraseña temporal
    caracteres = string.ascii_letters + string.digits
    nueva_pass = ''.join(random.choice(caracteres) for i in range(8))
    
    # 2. Guardamos en la bóveda
    cliente.password_hash = obtener_hash_password(nueva_pass)
    db.commit()

    # 3. Devolvemos la clave a la página web directamente
    return {"mensaje": "Proceso completado.", "nueva_pass": nueva_pass}


class CambioPasswordReq(BaseModel):
    password_actual: str
    password_nueva: str

@app.post("/cambiar-password")
def cambiar_password(
    datos: schemas.CambioPasswordReq, 
    correo: str = Depends(verificar_token_cliente), 
    db: Session = Depends(get_db)
):
    # 1. Buscamos al cliente por el token de su sesión
    cliente = db.query(models.Cliente).filter(models.Cliente.correo == correo).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado.")
    
    # 2. Verificamos que sepa la contraseña actual (la temporal)
    if not verificar_password(datos.password_actual, cliente.password_hash):
        raise HTTPException(status_code=400, detail="La contraseña actual es incorrecta.")
    
    # 3. Validamos que la nueva sea segura
    if len(datos.password_nueva) < 6:
        raise HTTPException(status_code=400, detail="La nueva contraseña debe tener mínimo 6 caracteres.")
    
    # 4. Encriptamos y guardamos la nueva clave
    cliente.password_hash = obtener_hash_password(datos.password_nueva)
    db.commit()
    
    return {"mensaje": "Contraseña actualizada con éxito."}

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

@app.get("/mis-pedidos")
def obtener_mis_pedidos(correo: str = Depends(verificar_token_cliente), db: Session = Depends(get_db)):
    cliente = db.query(models.Cliente).filter(models.Cliente.correo == correo).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    
    # Buscamos los pedidos que coincidan con el celular del cliente registrado
    pedidos = db.query(models.Pedido).filter(models.Pedido.telefono == cliente.telefono).order_by(models.Pedido.fecha.desc()).all()
    
    resultado = []
    for p in pedidos:
        resultado.append({
            "folio": f"SJ-{p.id:04d}",
            "fecha": p.fecha.strftime("%d/%m/%Y"),
            "total": p.total,
            "estatus": p.estatus
        })
    return resultado

# ==========================================
# RUTAS DE CUPONES Y PERFIL
# ==========================================
@app.get("/mi-perfil")
def obtener_perfil(correo: str = Depends(verificar_token_cliente), db: Session = Depends(get_db)):
    cliente = db.query(models.Cliente).filter(models.Cliente.correo == correo).first()
    return cliente

@app.post("/validar-cupon")
def validar_cupon(datos: schemas.ValidarCuponReq, db: Session = Depends(get_db)):
    cupon = db.query(models.Cupon).filter(models.Cupon.codigo == datos.codigo.upper(), models.Cupon.activo == 1).first()
    if not cupon:
        raise HTTPException(status_code=404, detail="Cupón inválido o expirado.")
    return {"codigo": cupon.codigo, "porcentaje": cupon.porcentaje}

@app.get("/generar-cupon-prueba")
def generar_cupon_prueba(db: Session = Depends(get_db)):
    # Ejecuta esta ruta en tu navegador una sola vez para crear tu cupón
    existe = db.query(models.Cupon).filter(models.Cupon.codigo == "BIENVENIDA10").first()
    if not existe:
        nuevo = models.Cupon(codigo="BIENVENIDA10", porcentaje=10.0, activo=1)
        db.add(nuevo)
        db.commit()
        return {"mensaje": "¡Cupón BIENVENIDA10 (10% de descuento) creado y listo para usar!"}
    return {"mensaje": "El cupón ya existía."}

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
def crear_pago_seguro(pedido_req: schemas.PedidoSeguro, request: Request, db: Session = Depends(get_db)):
    total_pedido = 0
    items_para_banco = []
    
    # 1. VERIFICAR CUPÓN
    descuento_porc = 0.0
    if pedido_req.cupon:
        cupon_db = db.query(models.Cupon).filter(models.Cupon.codigo == pedido_req.cupon.upper(), models.Cupon.activo == 1).first()
        if cupon_db:
            descuento_porc = cupon_db.porcentaje

    for item in pedido_req.items:
        pantalon_db = db.query(models.Pantalon).filter(models.Pantalon.id == item.id).first()
        if not pantalon_db or pantalon_db.stock < item.cantidad:
            raise HTTPException(status_code=400, detail=f"Alguien acaba de comprar el último {item.nombre}")
        
        precio_con_descuento = float(item.precio) * (1.0 - (descuento_porc / 100.0))
        total_pedido += (precio_con_descuento * item.cantidad)
        
        items_para_banco.append({
            "title": f"[{item.codigo}] {item.nombre}",
            "quantity": item.cantidad,
            "unit_price": round(precio_con_descuento, 2),
            "currency_id": "MXN"
        })

    # 2. SISTEMA DE USUARIOS (Auto-guardado y Surprise Points)
    auth_header = request.headers.get("Authorization")
    cliente_db = None
    puntos_a_descontar = 0.0

    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            cliente_db = db.query(models.Cliente).filter(models.Cliente.correo == payload.get("sub")).first()
            if cliente_db:
                # Guardamos su dirección
                cliente_db.telefono = pedido_req.envio.telefono
                cliente_db.calle_numero = pedido_req.envio.calle_numero
                cliente_db.colonia = pedido_req.envio.colonia
                cliente_db.ciudad = pedido_req.envio.ciudad
                cliente_db.estado = pedido_req.envio.estado
                cliente_db.codigo_postal = pedido_req.envio.cp
                cliente_db.referencias_domicilio = pedido_req.envio.referencias
                
                # Descontamos puntos si lo solicitó
                if pedido_req.usar_puntos and cliente_db.puntos > 0:
                    puntos_a_descontar = cliente_db.puntos
                    cliente_db.puntos = 0.0 # Se vacía la bóveda de puntos al usarlos
                
                db.commit()
        except:
            pass

    # 3. APLICAR DESCUENTO DE PUNTOS AL TOTAL
    total_final = total_pedido - puntos_a_descontar
    if total_final < 0: total_final = 0

    # Si hay descuento por puntos, lo metemos como un "item negativo" para Mercado Pago
    if puntos_a_descontar > 0:
        items_para_banco.append({
            "title": "Descuento Surprise Points",
            "quantity": 1,
            "unit_price": round(-puntos_a_descontar, 2),
            "currency_id": "MXN"
        })

    # 4. CREAR PEDIDO
    nuevo_pedido = models.Pedido(
        nombre_cliente=pedido_req.envio.nombre, telefono=pedido_req.envio.telefono,
        calle_numero=pedido_req.envio.calle_numero, colonia=pedido_req.envio.colonia,
        ciudad=pedido_req.envio.ciudad, estado=pedido_req.envio.estado,
        codigo_postal=pedido_req.envio.cp, referencias=pedido_req.envio.referencias,
        total=total_final, estatus="PENDIENTE"
    )
    db.add(nuevo_pedido)
    db.commit()
    db.refresh(nuevo_pedido)

    for item in pedido_req.items:
        precio_final = float(item.precio) * (1.0 - (descuento_porc / 100.0))
        db.add(models.DetallePedido(
            pedido_id=nuevo_pedido.id, pantalon_id=item.id, 
            cantidad=item.cantidad, precio_unitario=round(precio_final, 2)
        ))
    
    # 5. REGALAR NUEVOS PUNTOS (5% del total pagado)
    if cliente_db:
        puntos_ganados = total_final * 0.05
        cliente_db.puntos += puntos_ganados
        db.commit()

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
    if respuesta["status"] != 201:
        raise HTTPException(status_code=400, detail="Mercado Pago bloqueó la solicitud.")

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
                    
                    # ⚡ ¡LA MAGIA DEL DIN! Disparamos la señal por el túnel
                    await manager.broadcast("NUEVO_PEDIDO")
                    
    return {"status": "procesado"}

@app.get("/simular-din")
async def simular_din():
    # Ruta secreta para que tú pruebes el sonido sin hacer una compra real
    await manager.broadcast("NUEVO_PEDIDO")
    return {"mensaje": "Señal enviada al centro de despacho."}

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
    
# ==========================================
# CENTRO DE DESPACHO (EXCLUSIVO YESSICA)
# ==========================================
@app.get("/pedidos-admin")
@limiter.limit("30/minute")
def obtener_pedidos_admin(request: Request, db: Session = Depends(get_db), token: str = Depends(verificar_token)):
    # Traemos todos los pedidos ordenados del más nuevo al más viejo
    pedidos = db.query(models.Pedido).order_by(models.Pedido.fecha.desc()).all()
    resultado = []
    
    for p in pedidos:
        lista_ropa = []
        for d in p.detalles:
            pantalon = db.query(models.Pantalon).filter(models.Pantalon.id == d.pantalon_id).first()
            lista_ropa.append({
                "cantidad": d.cantidad,
                "nombre": pantalon.nombre if pantalon else "Modelo eliminado",
                "codigo": pantalon.codigo if pantalon else "S/C"
            })
        
        resultado.append({
            "folio": f"SJ-{p.id:04d}",
            "cliente": p.nombre_cliente,
            "telefono": p.telefono,
            "direccion_completa": f"{p.calle_numero}, Col. {p.colonia}, {p.ciudad}, {p.estado}, C.P. {p.codigo_postal}",
            "referencias": p.referencias or "Sin referencias adicionales",
            "total": p.total,
            "estatus": p.estatus,
            "fecha": p.fecha.strftime("%d/%m/%Y"),
            "detalles": lista_ropa
        })
        
    return resultado

@app.get("/reset-db-total")
def reset_db_total():
    # Borrado forzado usando instrucción CASCADE de PostgreSQL
    with engine.begin() as conn:
        # 🟢 Agregamos 'clientes' a la lista de tablas a destruir
        conn.execute(text("DROP TABLE IF EXISTS detalles_pedido, pedidos, pantalones, categorias, clientes CASCADE;"))
        
    # Volvemos a construir la estructura limpia
    models.Base.metadata.create_all(bind=engine)
    return {"mensaje": "Base de datos formateada al 100%. Todo está limpio y listo para empezar."}

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

# ==========================================
# RUTA SECRETA PARA VERIFICAR BASE DE DATOS
# ==========================================
@app.get("/ver-clientes")
def ver_clientes(db: Session = Depends(get_db)):
    clientes = db.query(models.Cliente).all()
    resultado = []
    
    for c in clientes:
        resultado.append({
            "id": c.id,
            "nombre": c.nombre_completo,
            "correo": c.correo,
            "telefono": c.telefono,
            # Mostramos el hash para comprobar que la contraseña está blindada
            "password_encriptada": c.password_hash 
        })
        
    return resultado

@app.patch("/pantalones/{pantalon_id}/rapido")
def actualizar_pantalon_rapido(
    pantalon_id: int, datos: schemas.PantalonUpdateRapido,
    db: Session = Depends(get_db), token: str = Depends(verificar_token)
):
    pantalon = db.query(models.Pantalon).filter(models.Pantalon.id == pantalon_id).first()
    if not pantalon:
        raise HTTPException(status_code=404, detail="Modelo no encontrado")
    
    if datos.precio is not None:
        pantalon.precio = datos.precio
    if datos.stock is not None:
        pantalon.stock = datos.stock
        
    db.commit()
    return {"mensaje": "Inventario actualizado exitosamente"}

@app.patch("/pedidos/{pedido_id}/enviar")
def marcar_pedido_enviado(pedido_id: int, db: Session = Depends(get_db), token: str = Depends(verificar_token)):
    pedido = db.query(models.Pedido).filter(models.Pedido.id == pedido_id).first()
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    
    # Cambiamos el estatus
    pedido.estatus = "ENVIADO"
    db.commit()
    
    return {"mensaje": "Estatus actualizado a ENVIADO exitosamente"}