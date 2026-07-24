import os
from sqlalchemy import func, text
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from pydantic import BaseModel
import string
import random
import loyverse_sync
from fastapi.responses import Response
from reportlab.pdfgen import canvas
from datetime import datetime
from logistica_sync import generar_guia_envio
import threading
from fastapi.concurrency import run_in_threadpool
from fastapi import Body
from reportlab.graphics.barcode import code128
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import mm
from database import SessionLocal
from fastapi import APIRouter, Depends, HTTPException
from models import Pedido
from sqlalchemy import or_
import asyncio
from fastapi.staticfiles import StaticFiles 
import socket
import logging
import smtplib
from email.mime.application import MIMEApplication
from email.mime.text import MIMEText
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import shutil
from fastapi import FastAPI, Depends, File, UploadFile, Form, Request, HTTPException, status, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session  # <--- ¡ESTA ES LA LÍNEA QUE FALTABA!
import base64
import requests
import re
import pandas as pd
import hmac
import hashlib
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
import bcrypt
# Seguridad de Tráfico
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from email.mime.multipart import MIMEMultipart
import string
import random
from pydantic import BaseModel
import jwt
from datetime import datetime, timedelta, timezone
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi import WebSocket, WebSocketDisconnect
from fastapi import BackgroundTasks
import qrcode
from reportlab.lib.utils import ImageReader
from PIL import Image
import io

models.Base.metadata.create_all(bind=engine)
app = FastAPI(title="API Surprise Jeans - Fortificada")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

app.mount("/static", StaticFiles(directory="static"), name="static")
@app.on_event("startup")
async def iniciar_tareas_fondo():
    import asyncio
    loop = asyncio.get_event_loop()
    loop.create_task(robot_respaldos_diarios())
    print("🤖 Robot de respaldos inicializado.")

# ==========================================
# 📝 SISTEMA DE LOGS PROFESIONAL (Caja Negra)
# ==========================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("surprise_jeans.log"), # Guarda todo en un archivo
        logging.StreamHandler() # Sigue mostrando los mensajes en la consola de Render
    ]
)
logger = logging.getLogger("SurpriseJeans")


scheduler = AsyncIOScheduler()

def cron_recuperar_carritos():
    """ El robot revisará la base de datos automáticamente cada hora """
    db = SessionLocal()
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
    
    db = SessionLocal()
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

    scheduler.add_job(cron_respaldo_semanal, 'cron', day_of_week='sun', hour=3, minute=0)
    
    scheduler.start()
    print("⏰ Robot de Carritos y Reportes (APScheduler) Activado y Corriendo.")

# 1. ANTI-DDOS
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# 2. CORS SEGURO (Anti-Crash)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Permitimos el acceso desde el frontend
    allow_credentials=False, # ⚡ FIX: Apagamos esto para evitar el bloqueo interno de FastAPI
    allow_methods=["*"],
    allow_headers=["*"],
)

# 🚨 INYECTA TU TOKEN AQUÍ 🚨
MERCADO_PAGO_TOKEN = os.getenv("MERCADO_PAGO_TOKEN", "")
sdk = mercadopago.SDK(MERCADO_PAGO_TOKEN)

os.makedirs("static/uploads", exist_ok=True)

# ==========================================
# 🚨 SISTEMA DE LOGIN Y SEGURIDAD (JSON Web Tokens)
# ==========================================
ESTAMOS_EN_RENDER = os.getenv("RENDER")

if ESTAMOS_EN_RENDER:
    # 🔒 EN PRODUCCIÓN: Exigimos la llave real obligatoriamente
    SECRET_KEY = os.getenv("JWT_SECRET")
    if not SECRET_KEY:
        raise ValueError("🚨 ERROR FATAL: No configuraste JWT_SECRET en las variables de entorno de Render.")
else:
    # 💻 EN LOCAL (Tu Mac): Usamos una llave de repuesto para que puedas programar
    print("🔓 Modo local: Usando llave JWT de prueba.")
    SECRET_KEY = os.getenv("JWT_SECRET", "llave_secreta_local_para_pruebas")

# 👇 ESTAS LÍNEAS SE HABÍAN BORRADO, AQUÍ ESTÁN DE REGRESO 👇
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
    cliente = db.query(models.Cliente).filter(models.Cliente.correo == form_data.username).first()
    
    if not cliente or not verificar_password(form_data.password, cliente.password_hash):
        raise HTTPException(status_code=401, detail="Correo o contraseña incorrectos.")
    
    # ⚡ Access Token (Dura 15 minutos)
    exp_access = datetime.utcnow() + timedelta(minutes=15)
    access_token = jwt.encode({"sub": cliente.correo, "rol": "cliente", "id": cliente.id, "exp": exp_access}, SECRET_KEY, algorithm=ALGORITHM)
    
    # ⚡ Refresh Token (Dura 7 días)
    exp_refresh = datetime.utcnow() + timedelta(days=7)
    refresh_token = jwt.encode({"sub": cliente.correo, "rol": "cliente", "type": "refresh", "exp": exp_refresh}, SECRET_KEY, algorithm=ALGORITHM)
    
    return {
        "access_token": access_token, 
        "refresh_token": refresh_token,
        "token_type": "bearer", 
        "nombre": cliente.nombre_completo
    }

@app.post("/refresh-token")
def renovar_sesion(req: schemas.RefreshTokenReq):
    try:
        payload = jwt.decode(req.refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
        
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Token inválido para renovación.")
            
        nuevo_exp_access = datetime.utcnow() + timedelta(minutes=15)
        nuevo_access_token = jwt.encode(
            {"sub": payload.get("sub"), "rol": payload.get("rol"), "exp": nuevo_exp_access}, 
            SECRET_KEY, algorithm=ALGORITHM
        )
        
        return {"access_token": nuevo_access_token, "token_type": "bearer"}
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="El Refresh Token expiró. Inicia sesión de nuevo.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Refresh Token inválido.")

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
# 🚨 MOTOR DE CORREOS GMAIL SMTP (BLINDADO) 🚨
# ==========================================
def _enviar_async(correo_destino, asunto, html_content, gmail_user, gmail_password):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = asunto
    msg["From"] = f"Surprise Jeans <{gmail_user}>"
    msg["To"] = correo_destino
    msg.attach(MIMEText(html_content, "html"))

    try:
        # ⚡ BLINDAJE 1: Timeout de 4 segundos máximo (si Render lo bloquea, se rinde para no trabar el servidor)
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=4) as servidor:
            servidor.login(gmail_user, gmail_password)
            servidor.sendmail(gmail_user, correo_destino, msg.as_string())
        print(f"📧 Correo SMTP enviado con éxito a: {correo_destino}")
    except Exception as e:
        print(f"❌ Correo bloqueado (Posible restricción de Render): {e}")

def enviar_correo_gmail(correo_destino, asunto, html_content):
    gmail_user = os.getenv("GMAIL_USER", "denzellopezcabrera@gmail.com")
    gmail_password = os.getenv("GMAIL_PASSWORD", "") 
    
    if not gmail_password:
        print("Advertencia: GMAIL_PASSWORD no está configurada.")
        return False

    # ⚡ BLINDAJE 2: Disparamos el correo en un "hilo fantasma" paralelo. 
    # Así la clienta no se queda viendo la pantalla de carga trabada si Render bloquea el puerto.
    hilo = threading.Thread(target=_enviar_async, args=(correo_destino, asunto, html_content, gmail_user, gmail_password))
    hilo.start()
    
    return True
    
def enviar_correo_actualizacion_envio(correo_destino, nombre, folio, estatus_envio, guia, link_rastreo):
    mensajes = {
        "en_transito": "🚚 ¡Tu paquete ya está en camino! Ha salido de nuestro almacén y va directo a ti.",
        "entregado": "🎉 ¡Tu paquete ha sido entregado! Esperamos que disfrutes mucho tus Surprise Jeans."
    }
    
    mensaje_personalizado = mensajes.get(estatus_envio, "📦 Hay una actualización en el estado de tu paquete.")
    
    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: auto; padding: 20px; border: 1px solid #e5e7eb; border-radius: 12px;">
        <h2 style="color: #4f46e5; text-align: center; font-style: italic;">Surprise Jeans</h2>
        <h3 style="color: #111827; text-align: center;">Actualización de tu pedido SJ-{folio}</h3>
        <p style="color: #4b5563; font-size: 15px; text-align: center;">Hola {nombre}, {mensaje_personalizado}</p>
        <div style="background-color: #f9fafb; padding: 15px; text-align: center; border-radius: 8px; margin-top: 20px;">
            <p style="margin: 0; color: #6b7280;">Número de Guía:</p>
            <p style="font-size: 18px; font-weight: bold; color: #111827;">{guia}</p>
            <a href="{link_rastreo}" style="display: inline-block; margin-top: 15px; background-color: #10b981; color: white; padding: 10px 20px; text-decoration: none; border-radius: 6px; font-weight: bold;">Rastrear Paquete</a>
        </div>
    </div>
    """
    enviar_correo_gmail(correo_destino, f"Actualización de Envío - Pedido SJ-{folio}", html_content)

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

@app.post("/webhook/skydropx")
async def webhook_skydropx(request: Request, db: Session = Depends(get_db)):
    try:
        datos = await request.json()
        evento = datos.get("event_type")
        
        # Solo nos interesan las actualizaciones de estado de rastreo
        if evento == "tracker.updated":
            rastreo = datos.get("data", {})
            guia = rastreo.get("tracking_number")
            nuevo_estado = rastreo.get("status") # Puede ser "in_transit", "delivered", etc.
            
            # Buscamos el pedido en la base de datos usando la guía
            pedido = db.query(models.Pedido).filter(models.Pedido.guia_rastreo.ilike(f"%{guia}%")).first()
            
            if pedido:
                if nuevo_estado == "in_transit" and pedido.estatus != "EN_TRANSITO":
                    pedido.estatus = "EN_TRANSITO"
                    db.commit()
                    enviar_correo_actualizacion_envio(pedido.correo_cliente, pedido.nombre_cliente, f"{pedido.id:04d}", "en_transito", guia, pedido.guia_rastreo)
                    
                elif nuevo_estado == "delivered" and pedido.estatus != "ENTREGADO":
                    pedido.estatus = "ENTREGADO"
                    db.commit()
                    enviar_correo_actualizacion_envio(pedido.correo_cliente, pedido.nombre_cliente, f"{pedido.id:04d}", "entregado", guia, pedido.guia_rastreo)
                    
        return {"status": "procesado"}
    except Exception as e:
        logger.error(f"Error procesando webhook de Skydropx: {e}")
        return {"status": "error"}

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
        # Gafete de acceso (15 min)
        exp_access = datetime.utcnow() + timedelta(minutes=15)
        access_token = jwt.encode({"sub": "admin_yessica", "exp": exp_access}, SECRET_KEY, algorithm=ALGORITHM)
        
        # Llave maestra de renovación (7 días)
        exp_refresh = datetime.utcnow() + timedelta(days=7)
        refresh_token = jwt.encode({"sub": "admin_yessica", "type": "refresh", "exp": exp_refresh}, SECRET_KEY, algorithm=ALGORITHM)
        
        return {
            "access_token": access_token, 
            "refresh_token": refresh_token, 
            "token_type": "bearer"
        }
    raise HTTPException(status_code=400, detail="Contraseña incorrecta")

@app.get("/")
def inicio():
    return {"mensaje": "Servidor Seguro de Surprise Jeans Operativo 🔒"}

@app.get("/mis-pedidos")
def obtener_mis_pedidos(correo: str = Depends(verificar_token_cliente), db: Session = Depends(get_db)):
    cliente = db.query(models.Cliente).filter(models.Cliente.correo == correo).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    
    pedidos = db.query(models.Pedido).filter(models.Pedido.correo_cliente == cliente.correo).order_by(models.Pedido.fecha.desc()).all()
    
    resultado = []
    for p in pedidos:
        # ⚡ Extraemos la talla para que el cliente la vea en su recibo web
        ropa_comprada = []
        for d in p.detalles:
            nombre_base = d.pantalon.nombre if d.pantalon else "Modelo"
            nombre_final = f"{nombre_base} (Talla {d.talla})" if d.talla else nombre_base
            ropa_comprada.append({"id": d.pantalon_id, "nombre": nombre_final})
            
        resultado.append({
            "id": p.id, # ⚡ ¡ESTA ES LA LÍNEA MÁGICA QUE FALTABA!
            "folio": f"SJ-{p.id:04d}",
            "fecha": p.fecha.strftime("%d/%m/%Y"),
            "total": p.total,
            "estatus": p.estatus,
            "guia": p.guia_rastreo, 
            "ropa": ropa_comprada
        })
    return resultado

@app.get("/rastrear-pedido")
def rastrear_pedido(folio: str, contacto: str, db: Session = Depends(get_db)):
    # 1. Limpiamos el texto del folio
    try:
        pedido_id = int(folio.upper().replace("SJ-", ""))
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de folio inválido. Usa SJ-0000.")

    # 2. Buscamos el pedido usando el ID y comprobamos si coincide el correo O el teléfono
    pedido = db.query(Pedido).filter(
        Pedido.id == pedido_id,
        or_(Pedido.correo_cliente == contacto, Pedido.telefono == contacto)
    ).first()
    
    # 3. Si no existe, error 404
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido no encontrado o dato de contacto incorrecto")
        
    # 4. Formateamos la respuesta
    return {
        "folio": f"SJ-{pedido.id:04d}",
        "estatus": pedido.estatus,
        "guia": pedido.guia_rastreo,
        "tracking_number": getattr(pedido, 'tracking_number', None), 
        "tracking_url": getattr(pedido, 'tracking_url', None)     
    }

@app.post("/pantalones/{pantalon_id}/resenas")
def crear_resena(
    pantalon_id: int, datos: schemas.ResenaCrear, 
    correo: str = Depends(verificar_token_cliente), db: Session = Depends(get_db)
):
    cliente = db.query(models.Cliente).filter(models.Cliente.correo == correo).first()
    
    # 1. Verificar si realmente lo compró y ya se lo enviamos/cobramos
    compro = db.query(models.DetallePedido).join(models.Pedido).filter(
        models.Pedido.correo_cliente == cliente.correo,
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
    precio_min: Optional[float] = None, # ⚡ NUEVO: Rango inicial
    precio_max: Optional[float] = None, # ⚡ NUEVO: Rango límite
    orden: Optional[str] = None,        # ⚡ NUEVO: "precio_asc", "precio_desc", o "recientes"
    db: Session = Depends(get_db)
):
    logger.info("🗄️ BASE DE DATOS: Buscando catálogo con filtros avanzados...")
    query = db.query(models.Pantalon)
    
    # 1. Filtros exactos y de texto
    if categoria_id: query = query.filter(models.Pantalon.categoria_id == categoria_id)
    if busqueda: query = query.filter(models.Pantalon.nombre.ilike(f"%{busqueda}%"))
    
    # 2. ⚡ Filtros de Presupuesto
    if precio_min is not None: query = query.filter(models.Pantalon.precio >= precio_min)
    if precio_max is not None: query = query.filter(models.Pantalon.precio <= precio_max)
    
    # 3. ⚡ Algoritmos de Ordenamiento
    if orden == "precio_asc":
        query = query.order_by(models.Pantalon.precio.asc()) # Los más baratos primero
    elif orden == "precio_desc":
        query = query.order_by(models.Pantalon.precio.desc()) # Los más caros primero
    else: 
        query = query.order_by(models.Pantalon.id.desc()) # "recientes" por defecto
        
    resultados = query.offset(skip).limit(limit).all()
    return resultados

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
    ).subquery().select()

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
    p.setFont("Helvetica-Bold", 16)
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

    # ⚡ EL TOQUE PERSONAL DE YESSICA (Firmas y Logo)
    p.setFont("Times-Italic", 14)
    p.drawString(10*mm, 32*mm, "Muchas gracias por tu compra ♥")
    
    # Simulando el logo "Surprise by YSK"
    p.setFont("Times-BoldItalic", 18)
    p.drawString(10*mm, 23*mm, "Surprise")
    p.setFont("Helvetica-Bold", 10)
    p.drawString(35*mm, 23*mm, "- by YSK")

    # Código de Barras (Se baja para no chocar con las firmas)
    barcode = code128.Code128(f"SJ-{pedido.id:04d}", barHeight=12*mm, barWidth=1.5)
    barcode.drawOn(p, 10*mm, 6*mm)

    p.showPage()
    p.save()
    buffer.seek(0)
    
    # 3. Enviamos el archivo listo para imprimir
    return Response(content=buffer.getvalue(), media_type="application/pdf")

async def robot_respaldos_diarios():
    """ Despierta cada 24 horas para hacer un backup y ENVIARLO POR CORREO a salvo de Render """
    while True:
        # 86400 segundos = 24 horas
        await asyncio.sleep(86400) 
        try:
            db = SessionLocal()
            pedidos = db.query(models.Pedido).all()
            clientes = db.query(models.Cliente).all()
            
            fecha = datetime.now().strftime("%Y-%m-%d")
            
            respaldo = {
                "fecha_respaldo": fecha,
                "total_pedidos": len(pedidos),
                "total_clientes": len(clientes),
                "pedidos": [{"id": p.id, "folio": getattr(p, 'folio', p.id), "total": p.total, "estatus": p.estatus} for p in pedidos],
                "clientes": [{"id": c.id, "nombre": c.nombre_completo, "correo": c.correo} for c in clientes]
            }
            
            # Convertimos el diccionario a un archivo en memoria
            archivo_json = json.dumps(respaldo, ensure_ascii=False, indent=4).encode('utf-8')
            
            # ⚡ ENVIAMOS POR CORREO PARA NO DEPENDER DEL DISCO DE RENDER
            msg = MIMEMultipart()
            msg["Subject"] = f"🛡️ Respaldo Diario Automático - {fecha}"
            msg["From"] = f"Surprise Jeans <{os.getenv('GMAIL_USER')}>"
            msg["To"] = os.getenv('GMAIL_USER') # Te lo envías a ti mismo
            
            msg.attach(MIMEText("Adjunto el respaldo de seguridad de hoy. Este archivo está a salvo de los reinicios de Render.", "plain"))
            
            adjunto = MIMEApplication(archivo_json, Name=f"respaldo_sj_{fecha}.json")
            adjunto['Content-Disposition'] = f'attachment; filename="respaldo_sj_{fecha}.json"'
            msg.attach(adjunto)
            
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as servidor:
                servidor.login(os.getenv("GMAIL_USER"), os.getenv("GMAIL_PASSWORD"))
                servidor.sendmail(os.getenv("GMAIL_USER"), os.getenv("GMAIL_USER"), msg.as_string())
                
            print(f"🛡️✅ Bóveda asegurada: Respaldo diario enviado por correo con éxito.")
        except Exception as e:
            print(f"❌ Error al crear el respaldo diario: {e}")
        finally:
            try:
                db.close()
            except:
                pass


# Cuando tengas tu cuenta, las pondrás en las variables de entorno de Render
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID", "")

def enviar_whatsapp_api(telefono_destino, texto_mensaje):
    """ Función maestra para disparar mensajes de WhatsApp por Meta API """
    # Si las variables están vacías, no hace nada (modo dormido)
    if not WHATSAPP_TOKEN or not WHATSAPP_PHONE_ID:
        print("⚠️ WhatsApp API apagada. Faltan credenciales.")
        return 

    # Limpiamos el teléfono (quitamos espacios y aseguramos que tenga la lada de México)
    telefono_limpio = "".join(filter(str.isdigit, str(telefono_destino)))
    if len(telefono_limpio) == 10:
        telefono_limpio = "52" + telefono_limpio 

    url = f"https://graph.facebook.com/v18.0/{WHATSAPP_PHONE_ID}/messages"
    
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": telefono_limpio,
        "type": "text",
        "text": {
            "preview_url": False,
            "body": texto_mensaje
        }
    }
    
    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        urllib.request.urlopen(req)
        print(f"✅ WA enviado silenciosamente a {telefono_limpio}")
    except Exception as e:
        # Extraemos el error exacto que nos dé Facebook
        error_msg = e.read().decode('utf-8') if hasattr(e, 'read') else str(e)
        print(f"❌ Error WhatsApp API: {error_msg}")

def enviar_alarma_inventario(nombre_modelo, talla, stock_actual):
    """ 🤖 Bot espía que avisa a Yessica si queda poco stock """
    if stock_actual <= 12:
        mensaje = f"🚨 *ALERTA DE INVENTARIO* 🚨\n\nYessica, el modelo *{nombre_modelo}* (Talla {talla}) se está agotando.\n\n⚠️ Solo quedan *{stock_actual} piezas* en bodega."
        # Usamos el número de la tienda que ya tienes en tus variables de entorno
        telefono_admin = os.getenv("WHATSAPP_NUMERO", "525513220695") 
        enviar_whatsapp_api(telefono_admin, mensaje)

async def auto_destruir_abandonado(pedido_id: int):
    """ Bomba de tiempo: Espera 30 minutos y si no hay pago, destruye el carrito """
    await asyncio.sleep(1800) # 1800 segundos = 30 minutos
    
    try:
        db = SessionLocal() 
        pedido = db.query(models.Pedido).filter(models.Pedido.id == pedido_id).first()
        
        if pedido and pedido.estatus == "PENDIENTE":
            db.delete(pedido)
            db.commit()
            
            # Hacemos sonar la campana para que desaparezca de tu pantalla Admin
            try:
                loop = asyncio.get_event_loop()
                loop.create_task(manager.broadcast("NUEVO_PEDIDO"))
            except:
                pass
    except Exception as e:
        pass
    finally:
        try:
            db.close()
        except:
            pass

@app.post("/crear-pago-seguro")
def crear_pago_seguro(request: Request, pedido_req: schemas.PedidoSeguro, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    try:
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
            total_item = float(item.precio) * item.cantidad 
            total_pedido += total_item
            
            precio_con_descuento = float(item.precio) * (1.0 - (descuento_porc / 100.0))
            items_para_banco.append({
                "title": f"[{item.codigo}] {item.nombre}",
                "quantity": item.cantidad, 
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

        # ⚡ 3. CÁLCULO DEL TOTAL FINAL (AHORA SÍ INCLUYE EL ENVÍO PARA MERCADO PAGO)
        costo_envio = getattr(pedido_req, 'costo_envio', 0.0)
        
        total_final = total_pedido * (1.0 - (descuento_porc / 100.0)) - puntos_a_descontar
        total_final = max(0.0, total_final) + costo_envio

        # ⚡ INYECTAMOS EL COSTO DE ENVÍO COMO UN "ARTÍCULO" PARA QUE EL BANCO LO COBRE
        if costo_envio > 0:
            paqueteria_nombre = getattr(pedido_req, 'paqueteria', 'Estándar')
            items_para_banco.append({
                "title": f"Envío ({paqueteria_nombre})",
                "quantity": 1,
                "unit_price": round(costo_envio, 2),
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

        # ⚡ ENCENDEMOS LA BOMBA DE TIEMPO DE 30 MINUTOS
        background_tasks.add_task(auto_destruir_abandonado, nuevo_pedido.id)

        lista_ropa = []
        for item in pedido_req.items:
            precio_final = float(item.precio) * (1.0 - (descuento_porc / 100.0))
            db.add(models.DetallePedido(
                pedido_id=nuevo_pedido.id, 
                pantalon_id=item.id, 
                cantidad=item.cantidad, 
                precio_unitario=round(precio_final, 2),
                sku_variante=item.sku_variante, 
                talla=item.talla                
            ))
            lista_ropa.append({"cantidad": item.cantidad, "nombre": f"{item.nombre} (Talla {item.talla})", "precio": round(precio_final, 2)})
        db.commit()
        
        # Puntos calculados estrictamente sobre la ropa, ignorando el envío
        puntos_ganados = max(0.0, total_final - costo_envio) * 0.05

        # 🚨 LA MAGIA: BYPASS DE INVENTARIO Y LOYVERSE 🚨
        if total_final <= 0 or pedido_req.cupon == "VENTA-PRESENCIAL":
            nuevo_pedido.estatus = "PAGADO"
            
            # ⚡ PUNTOS
            if cliente_db:
                cliente_db.puntos += puntos_ganados
                db.commit()

            # ⚡ RECIBO VIRTUAL Y BOT ESPÍA
            items_para_recibo = []
            for detalle in nuevo_pedido.detalles:
                # ⚡ FIX DEFINITIVO: Buscamos por ID interno y Talla
                variante_db = db.query(models.VarianteTalla).filter(
                    models.VarianteTalla.pantalon_id == detalle.pantalon_id,
                    models.VarianteTalla.talla == detalle.talla
                ).first()
                
                if variante_db and variante_db.stock >= detalle.cantidad:
                    # Descuento en tu base de datos local
                    variante_db.stock -= detalle.cantidad
                    if variante_db.pantalon:
                        variante_db.pantalon.stock -= detalle.cantidad 
                        
                    # ⚡ Descuento en la tablet Loyverse
                    background_tasks.add_task(loyverse_sync.descontar_stock_loyverse, variante_db.sku, variante_db.stock)
                        
                    items_para_recibo.append({
                        "sku": variante_db.sku, # Llave maestra
                        "cantidad": detalle.cantidad,
                        "precio": detalle.precio_unitario
                    })
                    
                    # 🤖 ACTIVAMOS EL BOT ESPÍA DE INVENTARIO
                    nombre_pantalon = variante_db.pantalon.nombre if variante_db.pantalon else "Modelo"
                    background_tasks.add_task(enviar_alarma_inventario, nombre_pantalon, variante_db.talla, variante_db.stock)

            if items_para_recibo:
                background_tasks.add_task(loyverse_sync.generar_recibo_virtual, nuevo_pedido.correo_cliente, nuevo_pedido.id, items_para_recibo, nuevo_pedido.total)
                
            db.commit()
            
            # Avisamos a las pantallas del despacho (Fix Asíncrono)
            background_tasks.add_task(manager.broadcast, "NUEVO_PEDIDO")
            
            # Escudo protector para que el correo no rompa la compra si falla
            if cliente_db:
                try:
                    enviar_correo_recibo(cliente_db.correo, cliente_db.nombre_completo, f"{nuevo_pedido.id:04d}", total_final, lista_ropa, puntos_ganados)
                except:
                    pass
                
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
        
        preference_response = sdk.preference().create(preference_data)
        return {"link_pago": preference_response["response"]["init_point"]}

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/webhook/mercadopago")
def webhook_mercadopago(background_tasks: BackgroundTasks, datos: dict = Body(...), db: Session = Depends(get_db)):
    # datos se extrae automáticamente, ya no bloquea el servidor
    
    if datos.get("type") == "payment":
        pago_id = datos.get("data", {}).get("id")
        info_pago = sdk.payment().get(pago_id)
        
        if info_pago["status"] == 200:
            estado_pago = info_pago["response"]["status"]
            metadata = info_pago["response"].get("metadata", {})
            pedido_id = metadata.get("pedido_interno_id")
            
            if estado_pago == "approved" and pedido_id:
                pedido_db = db.query(models.Pedido).filter(models.Pedido.id == pedido_id).first()
                
                if pedido_db and pedido_db.estatus in ["PENDIENTE", "RECORDATORIO_ENVIADO"]:
                    pedido_db.estatus = "PAGADO"
                    pedido_db.pago_id = str(pago_id) # ⚡ GUARDAMOS LA LLAVE AQUÍ
                    lista_ropa = []

                    # ⚡ EL FIX 3.0: RECIBOS VIRTUALES COMPLETOS
                    items_para_recibo = []
                    
                    for detalle in pedido_db.detalles:
                        # ⚡ FIX DEFINITIVO: Buscamos por ID interno y Talla
                        variante_db = db.query(models.VarianteTalla).filter(
                            models.VarianteTalla.pantalon_id == detalle.pantalon_id,
                            models.VarianteTalla.talla == detalle.talla
                        ).first()
                        
                        if variante_db and variante_db.stock >= detalle.cantidad:
                            # Descuenta localmente en tu servidor web
                            variante_db.stock -= detalle.cantidad
                            if variante_db.pantalon:
                                variante_db.pantalon.stock -= detalle.cantidad 
                            
                            # ⚡ Descuento en la tablet Loyverse
                            background_tasks.add_task(loyverse_sync.descontar_stock_loyverse, variante_db.sku, variante_db.stock)

                            # Guardamos el item para el recibo de Loyverse
                            items_para_recibo.append({
                                "sku": variante_db.sku, # Usamos la llave maestra de la base de datos
                                "cantidad": detalle.cantidad,
                                "precio": detalle.precio_unitario
                            })

                            # 🤖 ACTIVAMOS EL BOT ESPÍA DE INVENTARIO
                            nombre_pantalon = variante_db.pantalon.nombre if variante_db.pantalon else "Modelo"
                            background_tasks.add_task(enviar_alarma_inventario, nombre_pantalon, variante_db.talla, variante_db.stock)
                        
                        nombre_base = detalle.pantalon.nombre if detalle.pantalon else "Modelo"
                        nombre_final = f"{nombre_base} (Talla {detalle.talla})" if detalle.talla else nombre_base
                        lista_ropa.append({"cantidad": detalle.cantidad, "nombre": nombre_final, "precio": detalle.precio_unitario})
                    
                    # 🎉 DISPARAMOS EL RECIBO VIRTUAL EN LOYVERSE 🎉
                    if items_para_recibo:
                        background_tasks.add_task(loyverse_sync.generar_recibo_virtual, pedido_db.correo_cliente, pedido_db.id, items_para_recibo, pedido_db.total)
                    
                    db.commit()
                    
                    # Sonido Din por WebSocket
                    import asyncio
                    try:
                        loop = asyncio.get_event_loop()
                        loop.create_task(manager.broadcast("NUEVO_PEDIDO"))
                    except:
                        pass

                    try:
                        background_tasks.add_task(procesar_logistica_asincrona, pedido_db.id)
                    except:
                        pass
                    
                    # 🎁 GESTIÓN DE SURPRISE POINTS (SOLO PAGOS APROBADOS)
                    cliente_db = db.query(models.Cliente).filter(models.Cliente.correo == pedido_db.correo_cliente).first()
                    puntos_ganados = pedido_db.total * 0.05
                    
                    if cliente_db:
                        # Solo SUMAMOS los puntos ganados (Lo que gastó ya se descontó antes)
                        cliente_db.puntos += puntos_ganados
                        db.commit()
                    
                    # 📧 ENVIAR CORREO
                    if pedido_db.correo_cliente:
                        try:
                            enviar_correo_recibo(pedido_db.correo_cliente, pedido_db.nombre_cliente, f"{pedido_db.id:04d}", pedido_db.total, lista_ropa, puntos_ganados)
                        except:
                            pass

    return {"status": "procesado"}

@app.post("/admin/pedidos/{pedido_id}/reembolsar")
def reembolsar_pedido(
    pedido_id: int, 
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db), 
    token: str = Depends(verificar_token)
):
    pedido = db.query(models.Pedido).filter(models.Pedido.id == pedido_id).first()
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
        
    if pedido.estatus == "REEMBOLSADO":
        raise HTTPException(status_code=400, detail="El pedido ya fue reembolsado anteriormente.")
        
    # 1. Hablar con Mercado Pago
    if pedido.pago_id:
        respuesta_mp = sdk.refund().create(pedido.pago_id)
        if respuesta_mp["status"] not in [200, 201]:
            raise HTTPException(status_code=400, detail="Error en Mercado Pago: No se pudo procesar el reembolso.")
            
    # 2. Actualizar el estatus
    pedido.estatus = "REEMBOLSADO"
    
    # 3. Devolver Inventario Físico y Web
    for detalle in pedido.detalles:
        pantalon = db.query(models.Pantalon).filter(models.Pantalon.id == detalle.pantalon_id).first()
        if pantalon:
            # Regresamos el stock web
            pantalon.stock += detalle.cantidad 
            db.commit()
            
            # ⚡ Regresamos el stock en Loyverse asíncronamente
            background_tasks.add_task(loyverse_sync.descontar_stock_loyverse, pantalon.codigo, pantalon.stock)
            
    # 4. Quitar puntos ganados al cliente (Protección anti-fraude)
    cliente = db.query(models.Cliente).filter(models.Cliente.correo == pedido.correo_cliente).first()
    if cliente:
        puntos_a_quitar = pedido.total * 0.05
        cliente.puntos = max(0.0, cliente.puntos - puntos_a_quitar)
        db.commit()
        
    return {"mensaje": f"Reembolso del pedido SJ-{pedido.id:04d} procesado exitosamente. Inventario restaurado."}

# Ubica esta función en tu main.py (cerca de la línea 660 aproximadamente)
def procesar_logistica_asincrona(pedido_id: int):
    # Abrimos una sesión nueva y exclusiva para el hilo secundario
    db = SessionLocal()
    try:
        pedido = db.query(models.Pedido).filter(models.Pedido.id == pedido_id).first()
        if not pedido: return

        direccion = {
            "estado": pedido.estado, "ciudad": pedido.ciudad,
            "codigo_postal": pedido.codigo_postal, "calle_y_numero": pedido.calle_numero,
            "telefono": pedido.telefono, "email": pedido.correo_cliente
        }

        guia = generar_guia_envio(pedido.id, pedido.nombre_cliente, direccion)

        if guia:
            pedido.guia_rastreo = guia["tracking_url"]
            db.commit()
            logger.info(f"✅ Pedido {pedido_id} listo. Guía: {guia['tracking_number']}")
        else:
            pedido.estatus = "ERROR_LOGISTICA"
            db.commit()
            logger.error(f"❌ Falló logística en pedido {pedido_id}")
    finally:
        # Siempre cerramos la conexión al terminar
        db.close()

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
    # ⚡ 1. SEGURIDAD CRIPTOGRÁFICA
    secreto_loyverse = os.getenv("LOYVERSE_WEBHOOK_SECRET", "")
    
    if secreto_loyverse:
        body_bytes = await request.body()
        firma_recibida = request.headers.get("Loyverse-Signature", "")
        firma_calculada = base64.b64encode(
            hmac.new(secreto_loyverse.encode('utf-8'), body_bytes, hashlib.sha256).digest()
        ).decode('utf-8')
        
        if not hmac.compare_digest(firma_recibida, firma_calculada):
            print("🚨 INTENTO DE HACKEO BLOQUEADO EN WEBHOOK")
            raise HTTPException(status_code=403, detail="Firma criptográfica inválida")

    # 2. PROCESAMIENTO DIRECTO
    try:
        datos = await request.json()
        eventos = [datos] if "type" in datos else datos.get("events", [])
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
    # 1. Limpiamos espacios extra por si acaso
    nombre_limpio = nombre.strip()
    
    # 2. ⚡ ESCUDO: Revisamos si ya existe (ignorando mayúsculas/minúsculas)
    categoria_existente = db.query(models.Categoria).filter(models.Categoria.nombre.ilike(nombre_limpio)).first()
    
    if categoria_existente:
        raise HTTPException(status_code=400, detail=f"La categoría '{nombre_limpio}' ya existe en el sistema.")
        
    # 3. Si no existe, la guardamos sin problema
    nueva_categoria = models.Categoria(nombre=nombre_limpio)
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
def crear_pantalon(
    request: Request, 
    background_tasks: BackgroundTasks, 
    codigo: str = Form(...), 
    nombre: str = Form(...), 
    precio: float = Form(...),
    stock: int = Form(...), 
    categoria_id: int = Form(...), 
    color: str = Form("Original"), # ⚡ RECIBE EL COLOR
    foto: UploadFile = File(...),
    db: Session = Depends(get_db), 
    token: str = Depends(verificar_token)
):
    # 1. COMPRESIÓN WEBP Y SUBIDA A IMGBB MÁGICA
    contenido_original = foto.file.read()
    
    try:
        # Abrimos la foto pesada original
        imagen_pil = Image.open(io.BytesIO(contenido_original))
        
        # La convertimos a formato RGB (por si era un PNG con transparencia)
        if imagen_pil.mode in ("RGBA", "P"):
            imagen_pil = imagen_pil.convert("RGB")
            
        # Creamos un archivo temporal en la memoria RAM
        buffer_webp = io.BytesIO()
        
        # Guardamos la imagen como WebP con 80% de calidad (Compresión masiva)
        imagen_pil.save(buffer_webp, format="webp", quality=80)
        buffer_webp.seek(0)
        
        # Extraemos la nueva foto ultraligera
        contenido_comprimido = buffer_webp.read()
    except Exception as e:
        print(f"Error comprimiendo imagen: {e}. Usando original.")
        contenido_comprimido = contenido_original # Respaldo de seguridad

    imagen_base64 = base64.b64encode(contenido_comprimido).decode("utf-8")
    
    API_KEY = os.getenv("IMGBB_API_KEY", "")
    respuesta = requests.post("https://api.imgbb.com/1/upload", data={"key": API_KEY, "image": imagen_base64})
    
    if respuesta.status_code == 200: 
        url_permanente = respuesta.json()["data"]["url"]
    else: 
        return {"error": "Fallo la subida a ImgBB"}

    # ⚡ LIMPIEZA DE COLOR Y ARMADO DE PREFIJO
    color_limpio = color.strip()
    color_sku = color_limpio.replace(" ", "").upper()

    # Creamos al papá primero en BD
    nuevo_pantalon = models.Pantalon(
        codigo=codigo, nombre=nombre, precio=precio, 
        stock=stock, categoria_id=categoria_id, imagen_url=url_permanente
    )
    db.add(nuevo_pantalon)
    db.commit()
    db.refresh(nuevo_pantalon) # Refrescamos para obtener el ID del pantalón papá
    
    # --- ⚡ NUEVO BLOQUE: CREACIÓN DE TALLAS PARA LA BASE DE DATOS WEB ---
    paquetes = max(1, stock // 12) if stock > 0 else 0
    distribucion = {"3": 1, "5": 1, "7": 3, "9": 3, "11": 2, "13": 1, "15": 1}

    for talla_str, piezas_por_paquete in distribucion.items():
        stock_talla = paquetes * piezas_por_paquete
        sku_variante = f"{codigo}-{color_sku}-{talla_str}"

        nueva_variante = models.VarianteTalla(
            pantalon_id=nuevo_pantalon.id, 
            talla=talla_str, 
            color=color_limpio, # ⚡ GUARDAMOS EL COLOR
            stock=stock_talla, 
            sku=sku_variante
        )
        db.add(nueva_variante)

        if stock_talla > 0:
            background_tasks.add_task(loyverse_sync.descontar_stock_loyverse, sku_variante, stock_talla)

    db.commit()
    # ---------------------------------------------------------------------
    
    categoria_db = db.query(models.Categoria).filter(models.Categoria.id == categoria_id).first()
    nombre_cat = categoria_db.nombre if categoria_db else "Sin Categoría"
    
    # ⚡ LLAMADA A LOYVERSE INCLUYENDO EL COLOR
    background_tasks.add_task(loyverse_sync.crear_articulo_loyverse, nombre, codigo, precio, nombre_cat, color_limpio)

    return {"mensaje": "Pantalón subido y comprimido con éxito", "url": url_permanente}

@app.delete("/pantalones/{pantalon_id}")
@limiter.limit("15/minute")
def eliminar_pantalon(
    request: Request, 
    pantalon_id: int, 
    background_tasks: BackgroundTasks, 
    db: Session = Depends(get_db), 
    token: str = Depends(verificar_token)
):
    pantalon = db.query(models.Pantalon).filter(models.Pantalon.id == pantalon_id).first()
    if not pantalon: return {"error": "Pantalón no encontrado"}
    
    # ⚡ ENVIAMOS EL SKU DE LA PRIMERA TALLA PARA TENER PRECISIÓN LÁSER
    if pantalon.tallas and len(pantalon.tallas) > 0:
        sku_laser = pantalon.tallas[0].sku
        background_tasks.add_task(loyverse_sync.eliminar_articulo_loyverse, sku_laser)
    elif pantalon.codigo:
        # Respaldo por si es un pantalón viejo o un fantasma sin tallas
        background_tasks.add_task(loyverse_sync.eliminar_articulo_loyverse, pantalon.codigo)
        
    db.delete(pantalon)
    db.commit()
    return {"mensaje": "Pantalón eliminado de la web y de Loyverse"}

# ==========================================
# ⚡ RUTA DE CARGA MÁGICA DE FOTOS (100% SEGURA)
# ==========================================
@app.post("/pantalones/magico")
@limiter.limit("5/minute")
def subir_fotos_magicas(
    request: Request,
    background_tasks: BackgroundTasks,
    categoria_destino: str = Form("Nuevos"),
    archivos_fotos: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    token: str = Depends(verificar_token)
):
    API_KEY = os.getenv("IMGBB_API_KEY", "")
    if not API_KEY:
        raise HTTPException(status_code=500, detail="Falta configurar la llave de ImgBB en el servidor.")

    # 1. Revisamos si la categoría existe, si no, la creamos
    categoria = db.query(models.Categoria).filter(models.Categoria.nombre.ilike(categoria_destino)).first()
    if not categoria:
        categoria = models.Categoria(nombre=categoria_destino)
        db.add(categoria)
        db.commit()
        db.refresh(categoria)

    exitos = 0
    errores = 0

    for foto in archivos_fotos:
        # Extraemos el nombre sin la extensión (Ej: SJ-001_Skinny_350.jpg -> SJ-001_Skinny_350)
        nombre_base = foto.filename.rsplit('.', 1)[0]
        partes = nombre_base.split('_')
        
        if len(partes) < 3:
            errores += 1
            continue

        sku_padre = partes[0]
        # Regex para separar palabras pegadas (Ej: MomJeans -> Mom Jeans)
        nombre_limpio = re.sub(r'([a-z])([A-Z])', r'\1 \2', partes[1])
        
        try:
            precio = float(partes[2])
        except ValueError:
            errores += 1
            continue

        # Si trae color en el nombre, lo usamos; si no, es 'Original'
        color = "Original"
        if len(partes) >= 4:
            color = re.sub(r'([a-z])([A-Z])', r'\1 \2', partes[3])
        color_sku = color.replace(" ", "").upper()

        # 2. COMPRESIÓN WEBP Y SUBIDA A IMGBB
        contenido_original = foto.file.read()
        
        try:
            # Abrimos la foto pesada original
            imagen_pil = Image.open(io.BytesIO(contenido_original))
            
            # La convertimos a formato RGB (por si era un PNG con transparencia)
            if imagen_pil.mode in ("RGBA", "P"):
                imagen_pil = imagen_pil.convert("RGB")
                
            # Creamos un archivo temporal en la memoria RAM
            buffer_webp = io.BytesIO()
            
            # Guardamos la imagen como WebP con 80% de calidad (Compresión masiva)
            imagen_pil.save(buffer_webp, format="webp", quality=80)
            buffer_webp.seek(0)
            
            # Extraemos la nueva foto ultraligera
            contenido_comprimido = buffer_webp.read()
        except Exception as e:
            print(f"Error comprimiendo imagen: {e}. Usando original.")
            contenido_comprimido = contenido_original # Respaldo de seguridad

        imagen_base64 = base64.b64encode(contenido_comprimido).decode("utf-8")
        respuesta = requests.post("https://api.imgbb.com/1/upload", data={"key": API_KEY, "image": imagen_base64})
        
        if respuesta.status_code != 200:
            errores += 1
            continue
            
        url_permanente = respuesta.json()["data"]["url"]

        # 3. Guardamos el pantalón papá en la BD
        nuevo_pantalon = models.Pantalon(
            codigo=sku_padre, nombre=nombre_limpio, precio=precio, 
            stock=0, categoria_id=categoria.id, imagen_url=url_permanente
        )
        db.add(nuevo_pantalon)
        db.commit()
        db.refresh(nuevo_pantalon)

        # 4. Creamos las 7 tallas (hijos) con stock en 0
        distribucion = {"3": 1, "5": 1, "7": 3, "9": 3, "11": 2, "13": 1, "15": 1}
        for talla_str in distribucion.keys():
            sku_variante = f"{sku_padre}-{color_sku}-{talla_str}"
            nueva_variante = models.VarianteTalla(
                pantalon_id=nuevo_pantalon.id, 
                talla=talla_str, 
                color=color, 
                stock=0, 
                sku=sku_variante
            )
            db.add(nueva_variante)
        
        db.commit()

        # 5. Le avisamos a Loyverse que existe este modelo (en segundo plano)
        background_tasks.add_task(loyverse_sync.crear_articulo_loyverse, nombre_limpio, sku_padre, precio, categoria.nombre, color)
        
        exitos += 1

    return {"mensaje": f"Se subieron {exitos} modelos con éxito. Hubo {errores} archivos ignorados por mal formato."}

@app.post("/pantalones/excel")
@limiter.limit("5/minute") 
async def subir_excel(
    request: Request, 
    background_tasks: BackgroundTasks,
    archivo: UploadFile = File(...), 
    db: Session = Depends(get_db), 
    token: str = Depends(verificar_token)
):
    if not archivo.filename.endswith(('.xlsx', '.xls', '.csv')):
        return {"error": "El archivo debe ser un Excel o CSV"}
    contenido = await archivo.read()
    try:
        import pandas as pd
        from io import BytesIO
        
        # Aislamos la lectura pesada del Excel
        def procesar_pandas():
            if archivo.filename.endswith('.csv'): 
                return pd.read_csv(BytesIO(contenido))
            else: 
                return pd.read_excel(BytesIO(contenido))
                
        df = await run_in_threadpool(procesar_pandas)
        df.columns = df.columns.str.strip()
        
        columnas_esperadas = ["Codigo", "Nombre", "Precio", "Stock", "Categoria", "Foto_URL"]
        for col in columnas_esperadas:
            if col not in df.columns: return {"error": f"Falta la columna '{col}'"}

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

            codigo = str(fila['Codigo']).strip()
            nombre = str(fila['Nombre']).strip()
            precio = float(fila['Precio'])
            stock = int(fila['Stock'])
            
            # ⚡ LECTURA DEL COLOR
            color_excel = str(fila.get('Color', 'Original')).strip()
            if color_excel == 'nan' or not color_excel:
                color_excel = "Original"
            color_sku = color_excel.replace(" ", "").upper()

            # 1. CREAMOS AL PAPÁ PRIMERO
            nuevo_pantalon = models.Pantalon(
                codigo=codigo, nombre=nombre, precio=precio,
                stock=stock, categoria_id=categoria.id, imagen_url=foto_url
            )
            db.add(nuevo_pantalon)
            db.commit()
            db.refresh(nuevo_pantalon)
            
            pantalones_creados += 1
            
            # 2. AHORA SÍ, CREAMOS LOS HIJOS (Tallas) CON SU COLOR
            paquetes = max(1, stock // 12) if stock > 0 else 0
            distribucion = {"3": 1, "5": 1, "7": 3, "9": 3, "11": 2, "13": 1, "15": 1}

            for talla_str, piezas_por_paquete in distribucion.items():
                stock_talla = paquetes * piezas_por_paquete
                sku_variante = f"{codigo}-{color_sku}-{talla_str}"
                
                nueva_talla = models.VarianteTalla(
                    pantalon_id=nuevo_pantalon.id,
                    talla=talla_str,
                    color=color_excel, # ⚡ GUARDAMOS EL COLOR EN BD
                    stock=stock_talla,
                    sku=sku_variante
                )
                db.add(nueva_talla)
                
                if stock_talla > 0:
                    background_tasks.add_task(loyverse_sync.descontar_stock_loyverse, sku_variante, stock_talla)
            
            db.commit()
            
            # ⚡ CREAMOS EN LOYVERSE CON COLOR
            background_tasks.add_task(loyverse_sync.crear_articulo_loyverse, nombre, codigo, precio, categoria.nombre, color_excel)
            
        return {"mensaje": f"Carga masiva exitosa. Se crearon {pantalones_creados} modelos."}
        
    except Exception as e:
        return {"error": "Hubo un problema al leer el archivo."}
        
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
            nombre_base = pantalon.nombre if pantalon else "Modelo eliminado"
            
            # ⚡ EL FIX: Le mostramos la talla y el SKU exacto al equipo de empaque
            nombre_final = f"{nombre_base} (Talla {d.talla})" if d.talla else nombre_base
            codigo_final = d.sku_variante if d.sku_variante else (pantalon.codigo if pantalon else "S/C")
            
            lista_ropa.append({
                "cantidad": d.cantidad,
                "nombre": nombre_final,
                "codigo": codigo_final
            })
        
        resultado.append({
            "id": p.id,
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

@app.patch("/pedidos/{pedido_id}/enviar")
def enviar_pedido(pedido_id: int, guia_data: dict, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    # Buscamos el pedido
    pedido = db.query(models.Pedido).filter(models.Pedido.id == pedido_id).first()
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
        
    # Actualizamos base de datos
    pedido.estatus = "ENVIADO"
    pedido.guia = guia_data.get("guia", "")
    db.commit()

    # ⚡ ARMAMOS EL MENSAJE AUTOMÁTICO
    mensaje = f"¡Hola! 👋 Somos de *Surprise Jeans*.\n\nTe avisamos que tu pedido *SJ-{pedido.id:04d}* ya va en camino hacia ti 🚀.\n\n"
    if pedido.guia:
        mensaje += f"📦 Tu número de rastreo es: *{pedido.guia}*\n\n"
    mensaje += "¡Gracias por tu compra!"

    # ⚡ LE DECIMOS AL ROBOT QUE LO MANDE EN SEGUNDO PLANO
    background_tasks.add_task(enviar_whatsapp_api, pedido.telefono, mensaje)

    # ⚡ FIX DEFINITIVO: DELEGAR EL AVISO TELEPÁTICO A LAS TAREAS DE FONDO
    background_tasks.add_task(manager.broadcast, "ACTUALIZAR_ADMIN")

    return {"mensaje": "Pedido enviado y en proceso de notificación"}


@app.patch("/pedidos/{pedido_id}/entregar")
def marcar_pedido_entregado(pedido_id: int, db: Session = Depends(get_db)):
    # 1. Buscamos el pedido en la base de datos
    pedido = db.query(Pedido).filter(Pedido.id == pedido_id).first()
    
    # 2. Si no existe, mandamos error
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
        
    # 3. Cambiamos el estatus a ENTREGADO y guardamos
    pedido.estatus = "ENTREGADO"
    db.commit()
    
    return {"mensaje": "Pedido entregado con éxito"}

@app.get("/reset-db-total")
def reset_db_total():
    with engine.begin() as conn:
        if engine.name == "sqlite":
            conn.execute(text("DROP TABLE IF EXISTS variantes_talla, resenas, detalles_pedido, pedidos, pantalones, categorias, clientes, cupones;"))
        else:
            conn.execute(text("DROP TABLE IF EXISTS variantes_talla, resenas, detalles_pedido, pedidos, pantalones, categorias, clientes, cupones CASCADE;"))

    models.Base.metadata.create_all(bind=engine)
    return {"mensaje": "Base de datos formateada al 100%."}

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

@app.put("/pantalones/{pantalon_id}")
@limiter.limit("20/minute")
def editar_pantalon(  # ⚡ FIX: Quitamos el async para evitar bloqueos
    request: Request,
    pantalon_id: int,
    background_tasks: BackgroundTasks,
    codigo: str = Form(...),
    nombre: str = Form(...),
    precio: float = Form(...),
    stock: int = Form(...),
    categoria_id: int = Form(...),
    color: str = Form("Original"),
    foto: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    token: str = Depends(verificar_token)
):
    codigo_limpio = codigo.strip()
    color_limpio = color.strip()
    color_sku = color_limpio.replace(" ", "").upper()

    pantalon = db.query(models.Pantalon).filter(models.Pantalon.id == pantalon_id).first()
    if not pantalon:
        raise HTTPException(status_code=404, detail="Pantalón no encontrado")

    pantalon_existente = db.query(models.Pantalon).filter(
        models.Pantalon.codigo == codigo_limpio,
        models.Pantalon.id != pantalon_id
    ).first()
    
    if pantalon_existente:
        raise HTTPException(status_code=400, detail="¡Duplicado! Otro modelo ya usa ese código.")

    # 🚜 Eliminamos variantes viejas
    db.query(models.VarianteTalla).filter(models.VarianteTalla.pantalon_id == pantalon.id).delete(synchronize_session=False)
    
    # Borramos fantasmas globales con el nuevo formato
    skus_a_crear = [f"{codigo_limpio}-{color_sku}-{t}" for t in ["3", "5", "7", "9", "11", "13", "15"]]
    db.query(models.VarianteTalla).filter(models.VarianteTalla.sku.in_(skus_a_crear)).delete(synchronize_session=False)
    db.flush() 

    pantalon.codigo = codigo_limpio
    pantalon.nombre = nombre.strip()
    pantalon.precio = precio
    pantalon.stock = stock
    pantalon.categoria_id = categoria_id

    if foto and foto.filename:
        contenido = foto.file.read()  # ⚡ FIX: Lectura segura de la memoria
        imagen_base64 = base64.b64encode(contenido).decode("utf-8")
        API_KEY = os.getenv("IMGBB_API_KEY", "") # ⚡ FIX: Llave encriptada desde Render
        respuesta = requests.post("https://api.imgbb.com/1/upload", data={"key": API_KEY, "image": imagen_base64})
        if respuesta.status_code == 200:
            pantalon.imagen_url = respuesta.json()["data"]["url"]

    paquetes = max(1, stock // 12) if stock > 0 else 0
    distribucion = {"3": 1, "5": 1, "7": 3, "9": 3, "11": 2, "13": 1, "15": 1}

    for talla_str, piezas_por_paquete in distribucion.items():
        stock_talla = paquetes * piezas_por_paquete
        
        # ⚡ EL FIX: ARMAMOS EL SKU EXACTO PARA LOYVERSE
        sku_variante = f"{codigo_limpio}-{color_sku}-{talla_str}"

        nueva_variante = models.VarianteTalla(
            pantalon_id=pantalon.id, 
            talla=talla_str, 
            color=color_limpio, 
            stock=stock_talla, 
            sku=sku_variante
        )
        db.add(nueva_variante)

        if stock_talla >= 0:
            background_tasks.add_task(loyverse_sync.descontar_stock_loyverse, sku_variante, stock_talla)

    db.commit()
    categoria_db = db.query(models.Categoria).filter(models.Categoria.id == categoria_id).first()
    nombre_cat = categoria_db.nombre if categoria_db else "General"
    
    # Usamos la talla 3 como "Puntero Láser" para encontrar el artículo correcto en Loyverse
    sku_laser = f"{codigo_limpio}-{color_sku}-3" 
    background_tasks.add_task(loyverse_sync.actualizar_categoria_loyverse, sku_laser, nombre_cat)

    return {"mensaje": "Actualizado correctamente."}

@app.patch("/pantalones/{pantalon_id}/rapido")
@limiter.limit("30/minute")
def actualizacion_rapida(
    request: Request,
    pantalon_id: int, 
    datos: dict, 
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db), 
    token: str = Depends(verificar_token)
):
    pantalon = db.query(models.Pantalon).filter(models.Pantalon.id == pantalon_id).first()
    if not pantalon:
        raise HTTPException(status_code=404, detail="Pantalón no encontrado")
        
    if "precio" in datos:
        pantalon.precio = float(datos["precio"])
    if "stock" in datos:
        nuevo_stock = int(datos["stock"])
        pantalon.stock = nuevo_stock
        
        paquetes = max(1, nuevo_stock // 12) if nuevo_stock > 0 else 0
        distribucion = {"3": 1, "5": 1, "7": 3, "9": 3, "11": 2, "13": 1, "15": 1}
        
        for variante in pantalon.tallas:
            piezas = distribucion.get(variante.talla, 0)
            variante.stock = paquetes * piezas
            # ⚡ Usamos "variante.sku" directamente de la BD, así nunca se equivoca
            background_tasks.add_task(loyverse_sync.descontar_stock_loyverse, variante.sku, variante.stock)
            
    db.commit()
    return {"mensaje": "Stock y precio actualizados"}

# ==========================================
# 🚨 PUERTA SECRETA PARA VINCULAR LOYVERSE (MODO HACKER)
# ==========================================
@app.get("/vincular-loyverse")
def forzar_conexion_loyverse():
    url = "https://api.loyverse.com/v1.0/webhooks"
    token = os.getenv("LOYVERSE_TOKEN", "")    
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

@app.get("/test-alarma")
def probar_alarma_whatsapp():
    """ Ruta secreta para detonar un error a propósito y probar el bot """
    # Forzamos una excepción (error 500) para despertar al middleware
    raise Exception("Esta es una prueba de fuego del sistema de alarmas de Surprise Jeans 🔥")

def cron_respaldo_semanal():
    """ Robot que extrae la BD completa y te la manda por correo """
    db = SessionLocal()
    try:
        # 1. Empacamos el inventario y clientes
        pantalones = db.query(models.Pantalon).all()
        clientes = db.query(models.Cliente).all()
        
        datos_respaldo = {
            "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "inventario": [{"codigo": p.codigo, "nombre": p.nombre, "stock": p.stock} for p in pantalones],
            "clientes": [{"nombre": c.nombre_completo, "correo": c.correo, "telefono": c.telefono} for c in clientes]
        }
        
        archivo_json = json.dumps(datos_respaldo, indent=4).encode('utf-8')
        
        # 2. Preparamos el correo
        msg = MIMEMultipart()
        msg["Subject"] = f"📦 Respaldo Automático Surprise Jeans - {datetime.now().strftime('%d/%m/%Y')}"
        msg["From"] = f"Surprise Jeans <{os.getenv('GMAIL_USER')}>"
        msg["To"] = "denzellopezcabrera@gmail.com" 
        
        msg.attach(MIMEText("Adjunto el respaldo de seguridad de la base de datos de esta semana. Guárdalo bien 🔒.", "plain"))
        
        # 3. Adjuntamos el archivo
        adjunto = MIMEApplication(archivo_json, Name="Respaldo_Surprise.json")
        adjunto['Content-Disposition'] = 'attachment; filename="Respaldo_Surprise.json"'
        msg.attach(adjunto)
        
        # 4. Lo disparamos
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as servidor:
            servidor.login(os.getenv("GMAIL_USER"), os.getenv("GMAIL_PASSWORD"))
            servidor.sendmail(os.getenv("GMAIL_USER"), "denzellopezcabrera@gmail.com", msg.as_string())
            
        print("🗄️ Respaldo de seguridad enviado exitosamente por correo.")
    except Exception as e:
        print(f"❌ Error en robot de respaldos: {e}")
    finally:
        db.close()

@app.get("/test-logistica/{pedido_id}")
def probar_guia_skydropx(
    pedido_id: int, 
    background_tasks: BackgroundTasks, 
    db: Session = Depends(get_db)
):
    """ Ruta secreta para probar envíos sin pagar """
    pedido = db.query(models.Pedido).filter(models.Pedido.id == pedido_id).first()
    if not pedido:
        return {"error": f"El pedido {pedido_id} no existe en tu base de datos local."}
    
    # Simulamos lo que haría Mercado Pago
    background_tasks.add_task(procesar_logistica_asincrona, pedido.id)
    
    return {
        "mensaje": f"🚀 Disparando sistema logístico para el pedido {pedido.id}...",
        "instruccion": "Revisa la terminal (consola) de tu Mac en unos segundos para ver el link de la guía."
    }

@app.delete("/pedidos/{pedido_id}")
def eliminar_pedido_abandonado(pedido_id: int, db: Session = Depends(get_db)):
    pedido = db.query(models.Pedido).filter(models.Pedido.id == pedido_id).first()
    if pedido:
        db.delete(pedido)
        db.commit()
        return {"mensaje": "Carrito fantasma eliminado"}
    raise HTTPException(status_code=404)

# ==========================================
# 📄 GENERADOR DE RECIBOS PDF (CLIENTAS)
# ==========================================
@app.get("/pedidos/{pedido_id}/recibo")
def descargar_recibo_pdf(pedido_id: int, token: str, db: Session = Depends(get_db)):
    # 1. Validamos que el cliente haya iniciado sesión
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("rol") != "cliente": raise Exception()
        correo_cliente = payload.get("sub")
    except:
        raise HTTPException(status_code=401, detail="Token inválido")
    
    # 2. Verificamos que el pedido sea SUYO
    pedido = db.query(models.Pedido).filter(models.Pedido.id == pedido_id, models.Pedido.correo_cliente == correo_cliente).first()
    if not pedido: raise HTTPException(status_code=404, detail="Pedido no encontrado o acceso denegado")
    
    # 3. Dibujamos el PDF Tamaño Carta
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    ancho, alto = letter
    
    # Encabezado Corporativo
    p.setFont("Helvetica-Bold", 26)
    p.setFillColorRGB(0.31, 0.27, 0.90) # Tono Indigo 600
    p.drawString(50, alto - 60, "Surprise Jeans")
    
    p.setFont("Helvetica", 10)
    p.setFillColorRGB(0.5, 0.5, 0.5) # Gris
    p.drawString(50, alto - 75, "El fit perfecto diseñado para ti, directo de fábrica.")
    
    # Datos del Recibo
    p.setFont("Helvetica-Bold", 16)
    p.setFillColorRGB(0, 0, 0)
    p.drawString(ancho - 220, alto - 60, "RECIBO DE COMPRA")
    p.setFont("Helvetica", 12)
    p.drawString(ancho - 220, alto - 80, f"Folio: SJ-{pedido.id:04d}")
    p.drawString(ancho - 220, alto - 95, f"Fecha: {pedido.fecha.strftime('%d/%m/%Y')}")
    
    # Información de Facturación/Envío
    p.setFont("Helvetica-Bold", 12)
    p.drawString(50, alto - 130, "Facturado y enviado a:")
    p.setFont("Helvetica", 11)
    p.drawString(50, alto - 145, pedido.nombre_cliente.upper())
    p.drawString(50, alto - 160, f"Teléfono: {pedido.telefono}")
    p.drawString(50, alto - 175, f"{pedido.calle_numero}, Col. {pedido.colonia}")
    p.drawString(50, alto - 190, f"{pedido.ciudad}, {pedido.estado}. CP {pedido.codigo_postal}")
    
    # Tabla de Productos
    y = alto - 240
    p.setFont("Helvetica-Bold", 10)
    p.setFillColorRGB(0.2, 0.2, 0.2)
    p.drawString(50, y, "CANT.")
    p.drawString(100, y, "DESCRIPCIÓN DEL MODELO")
    p.drawString(ancho - 150, y, "P. UNITARIO")
    p.drawString(ancho - 80, y, "SUBTOTAL")
    
    p.line(50, y - 5, ancho - 50, y - 5) # Línea divisoria
    y -= 25
    
    # Llenamos la tabla
    p.setFont("Helvetica", 10)
    for detalle in pedido.detalles:
        pantalon = db.query(models.Pantalon).filter(models.Pantalon.id == detalle.pantalon_id).first()
        nombre = f"{pantalon.nombre} (Talla {detalle.talla})" if pantalon else f"Modelo (Talla {detalle.talla})"
        subtotal = detalle.cantidad * detalle.precio_unitario
        
        p.drawString(55, y, str(detalle.cantidad))
        p.drawString(100, y, nombre[:45]) # Cortamos si es muy largo
        p.drawString(ancho - 150, y, f"${detalle.precio_unitario:.2f}")
        p.drawString(ancho - 80, y, f"${subtotal:.2f}")
        y -= 20
        
    p.line(50, y, ancho - 50, y)
    y -= 25
    
    # Total
    p.setFont("Helvetica-Bold", 14)
    p.drawString(ancho - 150, y, "TOTAL MXN:")
    p.setFillColorRGB(0.06, 0.72, 0.50) # Verde esmeralda
    p.drawString(ancho - 80, y, f"${pedido.total:.2f}")
    
    p.showPage()
    p.save()
    buffer.seek(0)
    
    return Response(content=buffer.getvalue(), media_type="application/pdf")

# ==========================================
# 📱 ECOSISTEMA PHYGITAL: GENERADOR DE CÓDIGOS QR
# ==========================================
@app.get("/admin/etiquetas-qr")
def generar_etiquetas_qr(token: str, db: Session = Depends(get_db)):
    # 1. Validamos que solo Yessica pueda imprimir esto
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("sub") != "admin_yessica": raise Exception()
    except:
        raise HTTPException(status_code=401, detail="Pase VIP inválido")

    # 2. Traemos todos los pantalones que tienen stock
    pantalones = db.query(models.Pantalon).filter(models.Pantalon.stock > 0).all()
    
    # 3. Preparamos el lienzo PDF (Tamaño Carta)
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    ancho, alto = letter
    
    # Configuramos la cuadrícula (3 columnas x 4 filas)
    margen_x = 15 * mm
    margen_y = 20 * mm
    espacio_x = 65 * mm
    espacio_y = 60 * mm
    col = 0
    fila = 0
    
    p.setFont("Helvetica-Bold", 16)
    p.drawString(margen_x, alto - 15*mm, "Etiquetas Phygital - Surprise Jeans")
    
    y_base = alto - 65*mm # ✅ LÍNEA CORREGIDA (Bajamos los QRs 2.5 centímetros)
    
    for pantalon in pantalones:
        x = margen_x + (col * espacio_x)
        y = y_base - (fila * espacio_y)
        
        # ⚡ GENERACIÓN DEL CÓDIGO QR MÁGICO ⚡
        qr = qrcode.QRCode(version=1, box_size=10, border=1)
        # Este es el link que leerá el celular del cliente
        qr.add_data(f"https://surprisejeanysk.com/?producto={pantalon.id}")
        qr.make(fit=True)
        img_qr = qr.make_image(fill_color="black", back_color="white")
        
        buf_qr = BytesIO()
        img_qr.save(buf_qr, format="PNG")
        buf_qr.seek(0)
        
        # 4. Dibujamos el QR y los textos en el PDF
        p.drawImage(ImageReader(buf_qr), x, y, width=35*mm, height=35*mm)
        
        p.setFont("Helvetica-Bold", 10)
        p.drawString(x + 38*mm, y + 25*mm, pantalon.codigo)
        
        p.setFont("Helvetica", 8)
        nombre_corto = pantalon.nombre[:20] + "..." if len(pantalon.nombre) > 20 else pantalon.nombre
        p.drawString(x + 38*mm, y + 18*mm, nombre_corto)
        
        p.setFont("Helvetica-Bold", 12)
        p.setFillColorRGB(0.31, 0.27, 0.90) # Indigo
        p.drawString(x + 38*mm, y + 8*mm, f"${pantalon.precio:.2f}")
        p.setFillColorRGB(0, 0, 0) # Regresa a negro
        
        # Lógica de salto de cuadrícula y página
        col += 1
        if col > 2:
            col = 0
            fila += 1
            if fila > 3: # Caben 12 por página
                p.showPage()
                fila = 0
                y_base = alto - 65*mm # ✅ LÍNEA CORREGIDA
                p.setFont("Helvetica-Bold", 16)
                p.drawString(margen_x, alto - 15*mm, "Etiquetas Phygital - Surprise Jeans")

    p.save()
    buffer.seek(0)
    
    return Response(content=buffer.getvalue(), media_type="application/pdf")

# ==========================================
# 🌟 CARRUSEL DE RESEÑAS EN VIVO (PRUEBA SOCIAL)
# ==========================================
@app.get("/resenas/destacadas")
def obtener_resenas_destacadas(db: Session = Depends(get_db)):
    # 1. Buscamos reseñas con 4 o 5 estrellas que SÍ tengan un comentario escrito
    resenas = db.query(models.Resena, models.Cliente, models.Pantalon)\
        .join(models.Cliente, models.Resena.cliente_id == models.Cliente.id)\
        .join(models.Pantalon, models.Resena.pantalon_id == models.Pantalon.id)\
        .filter(models.Resena.calificacion >= 4)\
        .filter(models.Resena.comentario != None)\
        .filter(models.Resena.comentario != "")\
        .order_by(func.random())\
        .limit(10).all() # Máximo 10 al azar
    
    resultado = []
    for r, c, p in resenas:
        resultado.append({
            "estrellas": r.calificacion,
            "comentario": r.comentario,
            "cliente": c.nombre_completo.split(" ")[0], # Solo mostramos el primer nombre por privacidad
            "modelo": p.nombre,
            "imagen": p.imagen_url
        })
    return resultado

# ==========================================
# ⚡ LOGIN CON GOOGLE (SSO)
# ==========================================
class GoogleLoginReq(BaseModel):
    token: str

@app.post("/login-google")
def login_google(req: GoogleLoginReq, db: Session = Depends(get_db)):
    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=500, detail="Falta configurar GOOGLE_CLIENT_ID en Render.")
    
    try:
        # 1. Desencriptamos y validamos el token oficial de Google
        idinfo = id_token.verify_oauth2_token(req.token, google_requests.Request(), GOOGLE_CLIENT_ID)
        correo = idinfo.get('email')
        nombre = idinfo.get('name')
        
        # 2. ¿Existe la clienta en nuestra base de datos?
        cliente = db.query(models.Cliente).filter(models.Cliente.correo == correo).first()
        
        if not cliente:
            # 3. Si es nueva, la registramos mágicamente sin pedirle nada
            password_basura = ''.join(random.choice(string.ascii_letters) for i in range(16))
            
            cliente = models.Cliente(
                nombre_completo=nombre,
                correo=correo,
                password_hash=obtener_hash_password(password_basura), # Contraseña inaccesible
                telefono=""
            )
            db.add(cliente)
            db.commit()
            db.refresh(cliente)
            
            # La metemos a Loyverse silenciosamente
            try:
                import loyverse_sync
                loyverse_sync.crear_cliente_loyverse(nombre, correo, "")
            except Exception as e:
                # ⚡ AHORA SÍ NOS VA A IMPRIMIR EL ERROR EN RENDER
                print(f"❌ Error al enviar cliente a Loyverse desde Google: {e}")

        # 4. Le damos las llaves de acceso de Surprise Jeans
        # (Usamos tu función de crear_token existente si la tienes, o generamos los JWT directo)
        exp_access = datetime.now(timezone.utc) + timedelta(minutes=15)
        access_token = jwt.encode({"sub": cliente.correo, "rol": "cliente", "id": cliente.id, "exp": exp_access}, SECRET_KEY, algorithm=ALGORITHM)
        
        exp_refresh = datetime.now(timezone.utc) + timedelta(days=7)
        refresh_token = jwt.encode({"sub": cliente.correo, "rol": "cliente", "type": "refresh", "exp": exp_refresh}, SECRET_KEY, algorithm=ALGORITHM)
        
        return {
            "access_token": access_token, 
            "refresh_token": refresh_token,
            "token_type": "bearer", 
            "nombre": cliente.nombre_completo
        }
        
    except ValueError:
        raise HTTPException(status_code=401, detail="El Token de Google es inválido o ha expirado.")