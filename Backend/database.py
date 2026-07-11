import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Intentamos obtener la URL de la base de datos
URL_BASE_DATOS = os.getenv("DATABASE_URL")

# Render siempre crea una variable oculta llamada "RENDER" automáticamente
ESTAMOS_EN_RENDER = os.getenv("RENDER")

# 1. Si estamos en Render, EXIGIMOS Postgres. Si no está, que explote.
if ESTAMOS_EN_RENDER and not URL_BASE_DATOS:
    raise ValueError("¡ALERTA! El servidor está en Render pero falta la variable DATABASE_URL en Settings.")

# 2. Si NO estamos en Render (estás en tu Mac), usamos SQLite localmente para que puedas trabajar
if not URL_BASE_DATOS:
    print("💻 Modo local detectado: Usando base de datos SQLite de prueba en la Mac.")
    URL_BASE_DATOS = "sqlite:///./surprise_jeans.db"

# 3. Adaptador obligatorio para Postgres
if URL_BASE_DATOS.startswith("postgres://"):
    URL_BASE_DATOS = URL_BASE_DATOS.replace("postgres://", "postgresql://", 1)

# 4. Creación del motor dependiendo de la base de datos
if URL_BASE_DATOS.startswith("sqlite"):
    engine = create_engine(URL_BASE_DATOS, connect_args={"check_same_thread": False})
else:
    engine = create_engine(URL_BASE_DATOS)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()