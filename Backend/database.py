from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Le decimos que cree un archivo llamado surprise_jeans.db
URL_BASE_DATOS = "sqlite:///./surprise_jeans.db"

# Motor de conexión
engine = create_engine(URL_BASE_DATOS, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Esta función la usaremos después para abrir y cerrar la base de datos en cada petición
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()