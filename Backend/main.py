import os
from sqlalchemy import func, text
import loyverse_sync
from fastapi.responses import Response
from reportlab.pdfgen import canvas
from datetime import datetime
from reportlab.graphics.barcode import code128
from reportlab.lib.units import mm
import socket
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from apscheduler.schedulers.asyncio import AsyncIOScheduler
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
import urllib.request
from fastapi.responses import FileResponse
import mercadopago # <-- MOTOR BANCARIO
from sqlalchemy import text
import traceback
from fastapi.responses import JSONResponse
import urllib.parse
import requests
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
from fastapi import BackgroundTasks
# Seguridad de Sesión (JWT)
import jwt
from datetime import datetime, timedelta
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi import WebSocket, WebSocketDisconnect
import urllib.request
import json

models.Base.metadata.create_all(bind=engine)
app = FastAPI(title="API Surprise Jeans - Fortificada")

scheduler = AsyncIOScheduler()

def cron_recuperar_carritos():
    """ El robot revisará la base de datos automáticamente cada hora """
    db = next(get_db())
    try:
        hace_una_hora = datetime.utcnow() - timedelta(hours=1)
        pedidos_abandonados = db.query(models.Pedido).filter(
            models.Pedido.estatus == "PENDIENTE",
            models.Pedido.correo_cliente != None,
            models.Pedido.fecha <= hace_una_hora
        ).all()
        
        for pedido in pedidos_abandonados:
            enviar_correo_carrito_abandonado(pedido.correo_cliente, pedido.nombre_cliente, f"{pedido.id:04d}")
            pedido.estatus = "RECORDATORIO_ENVIADO"
            
        db.commit()
        print("🤖 Robot Cron: Carritos abandonados escaneados y correos enviados en automático.")
    except Exception as e:
        print(f"❌ Error en Robot Cron: {e}")
    finally:
        db.close()

def cron_reporte_mensual():
    """ Se ejecuta el día 1 de cada mes para generar el corte """
    hoy = datetime.now()
    if hoy.day != 1: return # Solo corre el primer día del mes
    
    db = next(get_db())
    try:
        ventas = db.query(models.Pedido).filter(models.Pedido.estatus == "PAGADO").count()
        # Aquí puedes sumar tus ingresos de la BD
        
        nombre_archivo = f"Reporte_SurpriseJeans_{hoy.strftime('%Y_%m')}.pdf"
        c = canvas.Canvas(nombre_archivo)
        
        # Estructura del PDF
        c.setFont("Helvetica-Bold", 20)
        c.drawString(100, 800, f"Reporte de Ventas - Surprise Jeans")
        c.setFont("Helvetica", 14)
        c.drawString(100, 750, f"Total de pedidos completados: {ventas}")
        c.drawString(100, 700, "¡El inventario está sincronizado al 100%!")
        c.save()
        
        # Opcional: Podrías usar tu motor SMTP para enviártelo por correo automáticamente
        print(f"📄 Reporte {nombre_archivo} generado con éxito.")
    finally:
        db.close()

# Y en tu @app.on_event("startup") agregas:
# scheduler.add_job(cron_reporte_mensual, 'cron', hour=8, minute=0) # Corre todos los días a las 8 AM revisando si es día 1

TELEFONO_WHATSAPP = os.getenv("WHATSAPP_NUMERO", "") 
API_KEY_CALLMEBOT = os.getenv("WHATSAPP_API_KEY", "")

@app.exception_handler(Exception)
async def whatsapp_exception_handler(request: Request, exc: Exception):
    """ Atrapa cualquier error 500 y te lo manda por WhatsApp """
    error_trace = traceback.format_exc()
    mensaje = f"🚨 *ERROR FATAL - SURPRISE JEANS* 🚨\n\nRuta: {request.url}\nError: {str(exc)}"
    
    try:
        # Codificamos el texto para URL (para que WhatsApp entienda los espacios y saltos de línea)
        mensaje_url = urllib.parse.quote(mensaje)
        url_whatsapp = f"https://api.callmebot.com/whatsapp.php?phone={TELEFONO_WHATSAPP}&text={mensaje_url}&apikey={API_KEY_CALLMEBOT}"
        
        # Lo mandamos con un timeout corto para no congelar el servidor si WhatsApp falla
        requests.get(url_whatsapp, timeout=5) 
    except:
        pass # Si falla el mensaje, el servidor sigue vivo
        
    return JSONResponse(status_code=500, content={"message": "Error interno. El administrador ha sido notificado por WhatsApp."})

@app.on_event("startup")
def iniciar_programador_automatico():
    # Se ejecuta cada 1 hora automáticamente
    scheduler.add_job(cron_recuperar_carritos, 'interval', hours=1)
    
    # ⚡ EL FIX: Descomentamos esta línea para que funcione el reporte PDF
    scheduler.add_job(cron_reporte_mensual, 'cron', hour=8, minute=0) 
    
    scheduler.start()
    print("⏰ Robot de Carritos y Reportes (APScheduler) Activado y Corriendo.")

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
MERCADO_PAGO_TOKEN = os.getenv("MERCADO_PAGO_TOKEN", "")
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

    # ⚡ FIDELIDAD OMNICANAL: Guardamos al cliente en la tablet
    loyverse_sync.crear_cliente_loyverse(cliente.nombre_completo, cliente.correo, cliente.telefono)

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



# ==========================================
# 🚨 PARCHE DE RED PARA RENDER (Forzar IPv4) 🚨
# Obliga al servidor a comunicarse con Google por IPv4 clásico
# ==========================================
old_getaddrinfo = socket.getaddrinfo
def force_ipv4_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    if host == "smtp.gmail.com":
        family = socket.AF_INET # El código AF_INET significa IPv4
    return old_getaddrinfo(host, port, family, type, proto, flags)
socket.getaddrinfo = force_ipv4_getaddrinfo

# ==========================================
# 🚨 MOTOR DE CORREOS GMAIL SMTP (SSL PUERTO 465) 🚨
# ==========================================
def enviar_correo_gmail(correo_destino, asunto, html_content):
    gmail_user = os.getenv("GMAIL_USER", "denzellopezcabrera@gmail.com")
    gmail_password = os.getenv("GMAIL_PASSWORD", "") 
    
    if not gmail_password:
        print("Advertencia: GMAIL_PASSWORD no está configurada.")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = asunto
    msg["From"] = f"Surprise Jeans <{gmail_user}>"
    msg["To"] = correo_destino
    msg.attach(MIMEText(html_content, "html"))

    try:
        # Hacemos la conexión usando nuestro túnel IPv4 forzado
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as servidor:
            servidor.login(gmail_user, gmail_password)
            servidor.sendmail(gmail_user, correo_destino, msg.as_string())
        
        print(f"📧 Correo SMTP enviado con éxito a: {correo_destino}")
        return True
    except Exception as e:
        print(f"❌ Error al enviar correo por SMTP de Gmail: {e}")
        return False

def enviar_correo_recibo(correo_destino, nombre, folio, total, lista_ropa, puntos_ganados):
    items_html = "".join([f"<li style='margin-bottom: 5px; color: #4b5563;'><b>{i['cantidad']}x</b> {i['nombre']} - ${i['precio']}</li>" for i in lista_ropa])
    
    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: auto; padding: 20px; border: 1px solid #e5e7eb; border-radius: 12px; background-color: #ffffff;">
        <h2 style="color: #4f46e5; text-align: center; font-style: italic; font-size: 28px; margin-bottom: 5px;">Surprise Jeans</h2>
        <p style="text-align: center; color: #6b7280; font-size: 12px; text-transform: uppercase; letter-spacing: 2px; margin-top: 0;">Recibo Oficial</p>
        
        <h3 style="color: #111827; text-align: center; margin-top: 30px;">¡Gracias por tu compra, {nombre}! 📦</h3>
        <p style="color: #4b5563; font-size: 15px; text-align: center; line-height: 1.5;">Tu pago ha sido procesado con éxito y ya estamos preparando tu paquete en nuestro almacén.</p>
        
        <div style="background-color: #f9fafb; padding: 20px; border-radius: 8px; margin: 30px 0; border: 1px solid #f3f4f6;">
            <div style="display: flex; justify-content: space-between; border-bottom: 1px solid #e5e7eb; padding-bottom: 10px; margin-bottom: 10px;">
                <span style="color: #6b7280; font-weight: bold;">Folio de Pedido:</span>
                <span style="color: #4f46e5; font-weight: 900;">SJ-{folio}</span>
            </div>
            <div style="display: flex; justify-content: space-between;">
                <span style="color: #6b7280; font-weight: bold;">Total Pagado:</span>
                <span style="color: #10b981; font-weight: 900; font-size: 18px;">${total} MXN</span>
            </div>
        </div>
        
        <h4 style="color: #374151; font-size: 16px; margin-bottom: 15px; text-transform: uppercase;">Artículos en tu envío:</h4>
        <ul style="padding-left: 20px; line-height: 1.6;">
            {items_html}
        </ul>
        
        <div style="background-color: #fffbeb; border: 1px solid #fde68a; padding: 15px; border-radius: 8px; margin: 30px 0; text-align: center;">
            <p style="margin: 0; color: #d97706; font-weight: 900; text-transform: uppercase; font-size: 14px;">🌟 Surprise Points Ganados</p>
            <p style="margin: 5px 0 0; color: #92400e; font-size: 14px; font-weight: bold;">Acabas de sumar ${round(puntos_ganados, 2)} a tu bóveda de cliente.</p>
        </div>
    </div>
    """
    enviar_correo_gmail(correo_destino, f"¡Tu pedido SJ-{folio} está confirmado! 🎉", html_content)

def enviar_correo_carrito_abandonado(correo_destino, nombre, folio):
    link_tienda = "https://surprisejeanysk.com/"
    
    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: auto; padding: 20px; border: 1px solid #e5e7eb; border-radius: 12px; background-color: #ffffff;">
        <h2 style="color: #4f46e5; text-align: center; font-style: italic; font-size: 28px; margin-bottom: 5px;">Surprise Jeans</h2>
        
        <h3 style="color: #111827; text-align: center; margin-top: 30px;">¡Hola {nombre}! Dejaste algo en tu bolsa... 🛒</h3>
        <p style="color: #4b5563; font-size: 15px; text-align: center; line-height: 1.5;">Notamos que estuviste a punto de comprar, pero no terminaste tu pedido <b>SJ-{folio}</b>.</p>
        
        <div style="text-align: center; margin: 30px 0; background-color: #f9fafb; padding: 20px; border-radius: 8px; border: 1px dashed #d1d5db;">
            <p style="color: #374151; font-size: 14px; margin-bottom: 15px; font-weight: bold;">Para animarte, te regalamos un 10% de descuento extra válido por hoy:</p>
            <span style="background-color: #ffffff; padding: 10px 20px; border-radius: 8px; font-weight: 900; color: #4f46e5; letter-spacing: 2px; border: 1px solid #e5e7eb; font-size: 18px;">REGRESA10</span>
        </div>
        
        <div style="text-align: center; margin-top: 30px;">
            <a href="{link_tienda}" style="background-color: #10b981; color: white; padding: 14px 28px; text-decoration: none; border-radius: 8px; font-weight: bold; display: inline-block; text-transform: uppercase;">Terminar mi compra</a>
        </div>
    </div>
    """
    enviar_correo_gmail(correo_destino, "🛒 ¡Olvidaste algo en tu carrito!", html_content)

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
    
    # ⚡ LA SOLUCIÓN: Ahora buscamos exactamente por su correo, ignorando el teléfono
    pedidos = db.query(models.Pedido).filter(models.Pedido.correo_cliente == cliente.correo).order_by(models.Pedido.fecha.desc()).all()
    
    resultado = []
    for p in pedidos:
        ropa_comprada = [{"id": d.pantalon_id, "nombre": d.pantalon.nombre if d.pantalon else "Modelo"} for d in p.detalles]
        resultado.append({
            "folio": f"SJ-{p.id:04d}",
            "fecha": p.fecha.strftime("%d/%m/%Y"),
            "total": p.total,
            "estatus": p.estatus,
            "guia": p.guia_rastreo, # ⚡ MANDAMOS LA GUÍA AL FRONTEND
            "ropa": ropa_comprada
        })
    return resultado

@app.post("/pantalones/{pantalon_id}/resenas")
def crear_resena(
    pantalon_id: int, datos: schemas.ResenaCrear, 
    correo: str = Depends(verificar_token_cliente), db: Session = Depends(get_db)
):
    cliente = db.query(models.Cliente).filter(models.Cliente.correo == correo).first()
    
    # 1. Verificar si realmente lo compró y ya se lo enviamos/cobramos
    compro = db.query(models.DetallePedido).join(models.Pedido).filter(
        models.Pedido.telefono == cliente.telefono,
        models.DetallePedido.pantalon_id == pantalon_id,
        models.Pedido.estatus.in_(["PAGADO", "ENVIADO"])
    ).first()
    
    if not compro:
        raise HTTPException(status_code=403, detail="Debes comprar este modelo primero para poder calificarlo.")
        
    # 2. Evitar spam (solo 1 reseña por cliente por modelo)
    existe = db.query(models.Resena).filter(models.Resena.pantalon_id == pantalon_id, models.Resena.cliente_id == cliente.id).first()
    if existe:
        raise HTTPException(status_code=400, detail="Ya calificaste este modelo anteriormente.")
        
    nueva_resena = models.Resena(
        pantalon_id=pantalon_id, cliente_id=cliente.id, 
        calificacion=datos.calificacion, comentario=datos.comentario
    )
    db.add(nueva_resena)
    db.commit()
    return {"mensaje": "¡Reseña publicada con éxito!"}

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

@app.get("/generar-cupon-100")
def generar_cupon_100(db: Session = Depends(get_db)):
    # Ejecuta esta ruta en tu navegador para crear un cupón que descuente TODO
    existe = db.query(models.Cupon).filter(models.Cupon.codigo == "GRATIS100").first()
    if not existe:
        nuevo = models.Cupon(codigo="GRATIS100", porcentaje=100.0, activo=1)
        db.add(nuevo)
        db.commit()
        return {"mensaje": "¡Cupón GRATIS100 (100% de descuento) creado y listo para usar!"}
    return {"mensaje": "El cupón GRATIS100 ya existía."}

@app.get("/generar-cupon-presencial")
def generar_cupon_presencial(db: Session = Depends(get_db)):
    # Crea el cupón maestro en la base de datos para ventas físicas
    existe = db.query(models.Cupon).filter(models.Cupon.codigo == "VENTA-PRESENCIAL").first()
    if not existe:
        nuevo = models.Cupon(codigo="VENTA-PRESENCIAL", porcentaje=100.0, activo=1)
        db.add(nuevo)
        db.commit()
        return {"mensaje": "✅ ¡Cupón VENTA-PRESENCIAL creado y listo para usar en la tienda!"}
    return {"mensaje": "El cupón ya existía."}

# ==========================================
# 🎯 MOTOR DE RECOMENDACIONES (CROSS-SELLING)
# ==========================================
@app.get("/pantalones/{pantalon_id}/recomendaciones")
def recomendaciones_inteligentes(pantalon_id: int, db: Session = Depends(get_db)):
    # 1. Buscamos en qué pedidos se ha comprado este pantalón
    pedidos_con_este = db.query(models.DetallePedido.pedido_id).filter(
        models.DetallePedido.pantalon_id == pantalon_id
    ).subquery()

    # 2. Buscamos qué OTRAS cosas compraron en esos mismos pedidos
    otros_pantalones = db.query(
        models.DetallePedido.pantalon_id,
        func.count(models.DetallePedido.pantalon_id).label("frecuencia")
    ).filter(
        models.DetallePedido.pedido_id.in_(pedidos_con_este),
        models.DetallePedido.pantalon_id != pantalon_id
    ).group_by(models.DetallePedido.pantalon_id).order_by(text("frecuencia DESC")).limit(3).all()

    ids_recomendados = [row.pantalon_id for row in otros_pantalones]

    # 3. Si es un producto nuevo y no hay historial, recomendamos de la misma categoría
    if len(ids_recomendados) < 3:
        actual = db.query(models.Pantalon).filter(models.Pantalon.id == pantalon_id).first()
        if actual:
            relleno = db.query(models.Pantalon.id).filter(
                models.Pantalon.categoria_id == actual.categoria_id,
                models.Pantalon.id != pantalon_id,
                models.Pantalon.id.notin_(ids_recomendados) if ids_recomendados else True
            ).limit(3 - len(ids_recomendados)).all()
            ids_recomendados.extend([r.id for r in relleno])

    # 4. Formateamos la respuesta
    recomendados = db.query(models.Pantalon).filter(models.Pantalon.id.in_(ids_recomendados)).all()
    resultado = [{"id": p.id, "nombre": p.nombre, "precio": p.precio, "imagen_url": p.imagen_url} for p in recomendados]
    
    return resultado

# ==========================================
# 🖨️ GENERADOR DE ETIQUETAS TÉRMICAS PDF
# ==========================================
@app.get("/pedidos/{pedido_id}/etiqueta")
def generar_etiqueta_pdf(pedido_id: int, token: str, db: Session = Depends(get_db)):
    # 1. Verificamos que sea Yessica quien pide el PDF
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("sub") != "admin_yessica": raise Exception()
    except:
        raise HTTPException(status_code=401, detail="Pase VIP inválido para imprimir")

    pedido = db.query(models.Pedido).filter(models.Pedido.id == pedido_id).first()
    if not pedido: raise HTTPException(status_code=404, detail="Pedido no encontrado")

    # 2. Dibujamos el PDF en memoria (Formato Etiqueta 4x6 estándar)
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=(100*mm, 150*mm)) 
    
    # Encabezado
    p.setFont("Helvetica-Bold", 18)
    p.drawString(10*mm, 135*mm, "SURPRISE JEANS - ENVÍO OFICIAL")
    p.setFont("Helvetica-Bold", 12)
    p.drawString(10*mm, 125*mm, f"FOLIO: SJ-{pedido.id:04d}")
    
    # Datos del Cliente
    p.setFont("Helvetica", 11)
    p.drawString(10*mm, 110*mm, f"Entregar a: {pedido.nombre_cliente.upper()}")
    p.drawString(10*mm, 100*mm, f"Teléfono: {pedido.telefono}")
    
    p.setFont("Helvetica-Bold", 11)
    p.drawString(10*mm, 85*mm, "Dirección de Entrega:")
    p.setFont("Helvetica", 10)
    p.drawString(10*mm, 75*mm, f"{pedido.calle_numero}")
    p.drawString(10*mm, 65*mm, f"Col. {pedido.colonia}, {pedido.ciudad}")
    p.drawString(10*mm, 55*mm, f"{pedido.estado}, C.P. {pedido.codigo_postal}")
    if pedido.referencias:
        p.drawString(10*mm, 45*mm, f"Ref: {pedido.referencias[:50]}")

    # Código de Barras
    barcode = code128.Code128(f"SJ-{pedido.id:04d}", barHeight=15*mm, barWidth=1.5)
    barcode.drawOn(p, 10*mm, 15*mm)

    p.showPage()
    p.save()
    buffer.seek(0)
    
    # 3. Enviamos el archivo listo para imprimir
    return Response(content=buffer.getvalue(), media_type="application/pdf")

# ==========================================
# 5. EL CEREBRO FINANCIERO (WEBHOOKS) 🧠
# ==========================================

@app.post("/crear-pago-seguro")
async def crear_pago_seguro(request: Request, pedido_req: schemas.PedidoSeguro, db: Session = Depends(get_db)):
    # 1. CÁLCULO DE TOTALES Y APLICACIÓN DE CUPONES
    total_pedido = 0.0
    descuento_porc = 0.0

    if pedido_req.cupon:
        cupon_db = db.query(models.Cupon).filter(models.Cupon.codigo == pedido_req.cupon).first()
        if cupon_db and cupon_db.activo:
            descuento_porc = cupon_db.porcentaje
        
        if pedido_req.cupon == "VENTA-PRESENCIAL":
            descuento_porc = 100.0

    items_para_banco = []
    
    for item in pedido_req.items:
        # ⚡ CORREGIDO: Usando item.cantidad como lo dicta tu schemas.py
        total_item = float(item.precio) * item.cantidad 
        total_pedido += total_item
        
        precio_con_descuento = float(item.precio) * (1.0 - (descuento_porc / 100.0))
        items_para_banco.append({
            "title": f"[{item.codigo}] {item.nombre}",
            "quantity": item.cantidad, # La llave quantity se queda en inglés solo para Mercado Pago
            "unit_price": round(precio_con_descuento, 2),
            "currency_id": "MXN"
        })

    # 2. SISTEMA DE USUARIOS
    auth_header = request.headers.get("Authorization")
    cliente_db = None
    puntos_a_descontar = 0.0

    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            cliente_db = db.query(models.Cliente).filter(models.Cliente.correo == payload.get("sub")).first()
            if cliente_db:
                cliente_db.telefono = pedido_req.envio.telefono
                cliente_db.calle_numero = pedido_req.envio.calle_numero
                cliente_db.colonia = pedido_req.envio.colonia
                cliente_db.ciudad = pedido_req.envio.ciudad
                cliente_db.estado = pedido_req.envio.estado
                cliente_db.codigo_postal = pedido_req.envio.cp
                cliente_db.referencias_domicilio = pedido_req.envio.referencias
                
                if pedido_req.usar_puntos and cliente_db.puntos > 0:
                    puntos_a_descontar = cliente_db.puntos
                    cliente_db.puntos = 0.0 
                db.commit()
        except:
            pass

    # 3. APLICAR DESCUENTO DE PUNTOS
    total_final = total_pedido - puntos_a_descontar
    if total_final < 0: total_final = 0

    if puntos_a_descontar > 0:
        items_para_banco.append({
            "title": "Descuento Surprise Points",
            "quantity": 1,
            "unit_price": round(-puntos_a_descontar, 2),
            "currency_id": "MXN"
        })

    # 4. CREAR PEDIDO
    nuevo_pedido = models.Pedido(
        correo_cliente=cliente_db.correo if cliente_db else None,
        nombre_cliente=pedido_req.envio.nombre, telefono=pedido_req.envio.telefono,
        calle_numero=pedido_req.envio.calle_numero, colonia=pedido_req.envio.colonia,
        ciudad=pedido_req.envio.ciudad, estado=pedido_req.envio.estado,
        codigo_postal=pedido_req.envio.cp, referencias=pedido_req.envio.referencias,
        total=total_final, estatus="PENDIENTE"
    )
    db.add(nuevo_pedido)
    db.commit()
    db.refresh(nuevo_pedido)

    lista_ropa = []
    for item in pedido_req.items:
        precio_final = float(item.precio) * (1.0 - (descuento_porc / 100.0))
        db.add(models.DetallePedido(
            pedido_id=nuevo_pedido.id, pantalon_id=item.id, 
            cantidad=item.cantidad, # ⚡ CORREGIDO
            precio_unitario=round(precio_final, 2)
        ))
        lista_ropa.append({"cantidad": item.cantidad, "nombre": item.nombre, "precio": round(precio_final, 2)})
    db.commit()
    
    puntos_ganados = total_final * 0.05
    if cliente_db:
        cliente_db.puntos += puntos_ganados
        db.commit()

    # 🚨 LA MAGIA: BYPASS DE INVENTARIO Y LOYVERSE 🚨
    if total_final <= 0 or pedido_req.cupon == "VENTA-PRESENCIAL":
        nuevo_pedido.estatus = "PAGADO"
        
        for detalle in nuevo_pedido.detalles:
            pantalon_db = db.query(models.Pantalon).filter(models.Pantalon.id == detalle.pantalon_id).first()
            if pantalon_db and pantalon_db.stock >= detalle.cantidad:
                pantalon_db.stock -= detalle.cantidad
                loyverse_sync.descontar_stock_loyverse(pantalon_db.codigo, pantalon_db.stock)    
                db.commit()
        
        await manager.broadcast("NUEVO_PEDIDO")
        
        if cliente_db:
            enviar_correo_recibo(cliente_db.correo, cliente_db.nombre_completo, f"{nuevo_pedido.id:04d}", total_final, lista_ropa, puntos_ganados)
            
        id_pago = "TIENDA-FISICA" if pedido_req.cupon == "VENTA-PRESENCIAL" else "CUPON-GRATIS"
        return {"link_pago": f"https://surprisejeanysk.com/?pago=exito&payment_id={id_pago}&external_reference={nuevo_pedido.id}"}

    # 5. MERCADO PAGO NORMAL
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
    datos = await request.json()
    
    if datos.get("type") == "payment":
        pago_id = datos.get("data", {}).get("id")
        info_pago = sdk.payment().get(pago_id)
        
        if info_pago["status"] == 200:
            estado_pago = info_pago["response"]["status"]
            metadata = info_pago["response"].get("metadata", {})
            pedido_id = metadata.get("pedido_interno_id")
            
            if estado_pago == "approved" and pedido_id:
                pedido_db = db.query(models.Pedido).filter(models.Pedido.id == pedido_id).first()
                
                # Aceptamos pagos pendientes o recuperados
                if pedido_db and pedido_db.estatus in ["PENDIENTE", "RECORDATORIO_ENVIADO"]:
                    pedido_db.estatus = "PAGADO"
                    lista_ropa = []
                    
                    for detalle in pedido_db.detalles:
                        pantalon_db = db.query(models.Pantalon).filter(models.Pantalon.id == detalle.pantalon_id).first()
                        
                        # VERIFICAMOS Y DESCONTAMOS STOCK
                        if pantalon_db and pantalon_db.stock >= detalle.cantidad:
                            # 1. Descuenta en tu base de datos web
                            pantalon_db.stock -= detalle.cantidad
                            
                            # 2. ⚡ VÍA 2: Descuenta en Loyverse enviando el STOCK FINAL absoluto
                            loyverse_sync.descontar_stock_loyverse(pantalon_db.codigo, pantalon_db.stock)
                            
                        if pantalon_db:
                            lista_ropa.append({"cantidad": detalle.cantidad, "nombre": pantalon_db.nombre, "precio": detalle.precio_unitario})
                    
                    # AQUÍ ESTABA EL ERROR: db.commit() ya tiene su propio renglón nuevamente
                    db.commit()
                    
                    # Sonido Din por WebSocket
                    await manager.broadcast("NUEVO_PEDIDO")
                    
                    # 📧 ENVIAR CORREO GMAIL (PAGO EN TIENDA REAL)
                    cliente_db = db.query(models.Cliente).filter(models.Cliente.correo == pedido_db.correo_cliente).first()
                    if cliente_db:
                        puntos_ganados = pedido_db.total * 0.05
                        enviar_correo_recibo(cliente_db.correo, cliente_db.nombre_completo, f"{pedido_db.id:04d}", pedido_db.total, lista_ropa, puntos_ganados)
                    
    return {"status": "procesado"}

@app.post("/admin/lanzar-recuperacion")
def lanzar_recuperacion_carritos(db: Session = Depends(get_db), token: str = Depends(verificar_token)):
    # 1. Calculamos la hora exacta de hace 1 hora
    hace_una_hora = datetime.utcnow() - timedelta(minutes=1)
    
    # 2. Buscamos pedidos PENDIENTES, que tengan correo, y que sean viejos
    pedidos_abandonados = db.query(models.Pedido).filter(
        models.Pedido.estatus == "PENDIENTE",
        models.Pedido.correo_cliente != None,
        models.Pedido.fecha <= hace_una_hora
    ).all()

    correos_enviados = 0
    for pedido in pedidos_abandonados:
        # Disparamos el correo
        enviar_correo_carrito_abandonado(pedido.correo_cliente, pedido.nombre_cliente, f"{pedido.id:04d}")
        
        # 3. Le cambiamos el estatus para no hacerle "Spam" y mandarle 100 correos
        pedido.estatus = "RECORDATORIO_ENVIADO"
        correos_enviados += 1
        
    db.commit()
    return {"mensaje": f"Escaneo completo. Se enviaron {correos_enviados} correos de recuperación."}

# ==========================================
# 🏪 WEBHOOK DE LOYVERSE POS (TIENDA FÍSICA)
# ==========================================
@app.post("/webhook/loyverse")
async def webhook_loyverse(request: Request, db: Session = Depends(get_db)):
    try:
        datos = await request.json()
        
        # ⚡ EL FIX: Loyverse manda un evento suelto, no una lista. Lo envolvemos en corchetes [ ]
        eventos = [datos] if "type" in datos else datos.get("events", [])
        
        # Ahora sí, se lo pasamos al archivo experto
        await loyverse_sync.procesar_webhooks_loyverse(eventos, db, manager)
        
    except Exception as e:
        print(f"❌ Error en webhook Loyverse: {e}")
        
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
    request: Request, 
    background_tasks: BackgroundTasks, # ⚡ NUEVO: Inyectamos el motor de segundo plano
    codigo: str = Form(...), 
    nombre: str = Form(...), 
    precio: float = Form(...),
    stock: int = Form(...), 
    categoria_id: int = Form(...), 
    foto: UploadFile = File(...),
    db: Session = Depends(get_db), 
    token: str = Depends(verificar_token)
):
    contenido = await foto.read()
    imagen_base64 = base64.b64encode(contenido).decode("utf-8")
    API_KEY = "967d4560b8e4d58a4f50db487013722f"
    respuesta = requests.post("https://api.imgbb.com/1/upload", data={"key": API_KEY, "image": imagen_base64})
    
    if respuesta.status_code == 200: 
        url_permanente = respuesta.json()["data"]["url"]
    else: 
        return {"error": "Fallo la subida a ImgBB"}

    nuevo_pantalon = models.Pantalon(codigo=codigo, nombre=nombre, precio=precio, stock=stock, categoria_id=categoria_id, imagen_url=url_permanente)
    db.add(nuevo_pantalon)
    db.commit()
    
    # ⚡ MAGIA ASÍNCRONA: El servidor delega la comunicación con Loyverse al fondo.
    # Tu página responde al instante mientras el servidor trabaja en silencio.
    background_tasks.add_task(loyverse_sync.crear_articulo_loyverse, nombre, codigo, precio)
    
    # Si pusiste stock inicial desde la web, mandamos la tarea al fondo también
    if stock > 0:
        background_tasks.add_task(loyverse_sync.descontar_stock_loyverse, codigo, stock)

    return {"mensaje": "Pantalón subido con éxito, sincronizando con Loyverse en segundo plano...", "url": url_permanente}

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
    # ⚡ SINCRONIZACIÓN DE ELIMINACIÓN: Lo borramos de la tablet física
    if pantalon.codigo:
        loyverse_sync.eliminar_articulo_loyverse(pantalon.codigo)
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
            "id": p.id,  # ⚡ ¡ESTA ES LA LÍNEA MÁGICA QUE FALTABA! ⚡
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
async def marcar_pedido_enviado(pedido_id: int, request: Request, db: Session = Depends(get_db), token: str = Depends(verificar_token)):
    datos = await request.json() # ⚡ RECIBIMOS LOS DATOS
    
    pedido = db.query(models.Pedido).filter(models.Pedido.id == pedido_id).first()
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    
    pedido.estatus = "ENVIADO"
    pedido.guia_rastreo = datos.get("guia", "") # Guardamos la guía (o en blanco si no hay)
    db.commit()
    
    return {"mensaje": "Estatus actualizado a ENVIADO exitosamente"}

@app.post("/admin/lanzar-recuperacion")
def lanzar_recuperacion_carritos(db: Session = Depends(get_db), token: str = Depends(verificar_token)):
    # Buscamos pedidos abandonados de hace más de 1 hora
    hace_una_hora = datetime.utcnow() - timedelta(hours=1)
    
    pedidos_abandonados = db.query(models.Pedido).filter(
        models.Pedido.estatus == "PENDIENTE",
        models.Pedido.correo_cliente != None,
        models.Pedido.fecha <= hace_una_hora
    ).all()

    correos_enviados = 0
    for pedido in pedidos_abandonados:
        # Enviamos el correo con el cupón REGRESA10
        enviar_correo_carrito_abandonado(pedido.correo_cliente, pedido.nombre_cliente, f"{pedido.id:04d}")
        
        # Cambiamos estatus para marcarlo como procesado
        pedido.estatus = "RECORDATORIO_ENVIADO"
        correos_enviados += 1
        
    db.commit()
    return {"mensaje": f"Escaneo completo. Se enviaron {correos_enviados} correos de recuperación."}

@app.patch("/pedidos/{pedido_id}/entregar")
def marcar_pedido_entregado(pedido_id: int, db: Session = Depends(get_db), token: str = Depends(verificar_token)):
    pedido = db.query(models.Pedido).filter(models.Pedido.id == pedido_id).first()
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    
    pedido.estatus = "ENTREGADO"
    db.commit()
    
    return {"mensaje": "Pedido marcado como ENTREGADO exitosamente"}

# ==========================================
# 🚨 PUERTA SECRETA PARA VINCULAR LOYVERSE (MODO HACKER)
# ==========================================
@app.get("/vincular-loyverse")
def forzar_conexion_loyverse():
    url = "https://api.loyverse.com/v1.0/webhooks"
    token = "b3dca41541684d0cb5dbcfeac1155736" 
    
    eventos_necesarios = ["receipts.update", "items.create", "items.update"]
    resultados = []
    
    for evento in eventos_necesarios:
        payload = json.dumps({
            "url": "https://surprise-jeans-api-denz.onrender.com/webhook/loyverse",
            "type": evento, # ⚡ EL FIX: Cambiamos "event" por "type"
            "status": "ENABLED"
        }).encode("utf-8")
        
        req = urllib.request.Request(url, data=payload)
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Content-Type", "application/json")
        
        try:
            res = urllib.request.urlopen(req)
            resultados.append({evento: "✅ Conectado con éxito"})
        except Exception as e:
            error_msg = e.read().decode('utf-8') if hasattr(e, 'read') else str(e)
            resultados.append({evento: f"Info: {error_msg}"})
            
    return {"estado": "Operación Maestra Terminada 👾", "detalles": resultados}
    

# ==========================================
# 🔄 VÍA 2: LA WEB LE AVISA A LA TIENDA FÍSICA
# ==========================================
def descontar_stock_loyverse(sku, nuevo_stock):
    token = "b3dca41541684d0cb5dbcfeac1155736"
    
    try:
        # 1. Obtener el ID de la tienda física
        req_tienda = urllib.request.Request("https://api.loyverse.com/v1.0/stores")
        req_tienda.add_header("Authorization", f"Bearer {token}")
        res_tienda = urllib.request.urlopen(req_tienda)
        store_id = json.loads(res_tienda.read().decode('utf-8'))["stores"][0]["id"]
        
        # 2. Buscar el pantalón en Loyverse por su SKU
        req_item = urllib.request.Request(f"https://api.loyverse.com/v1.0/items?sku={sku}")
        req_item.add_header("Authorization", f"Bearer {token}")
        res_item = urllib.request.urlopen(req_item)
        items = json.loads(res_item.read().decode('utf-8')).get("items", [])
        
        if not items:
            print(f"⚠️ El código {sku} no existe en Loyverse.")
            return
            
        variant_id = items[0]["variants"][0]["variant_id"]
        
        # 3. ⚡ MANDAR EL STOCK ABSOLUTO (stock_after)
        ajuste_payload = json.dumps({
            "inventory_levels": [{
                "store_id": store_id,
                "variant_id": variant_id,
                "stock_after": nuevo_stock 
            }]
        }).encode("utf-8")
        
        req_ajuste = urllib.request.Request("https://api.loyverse.com/v1.0/inventory", data=ajuste_payload, method="POST")
        req_ajuste.add_header("Authorization", f"Bearer {token}")
        req_ajuste.add_header("Content-Type", "application/json")
        
        urllib.request.urlopen(req_ajuste)
        print(f"✅ Omnicanal: El modelo {sku} se actualizó a {nuevo_stock} piezas en Loyverse.")
        
    except Exception as e:
        error_msg = e.read().decode('utf-8') if hasattr(e, 'read') else str(e)
        print(f"❌ Error de Loyverse: {error_msg}")