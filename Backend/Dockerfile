# 1. Usamos una imagen oficial de Python optimizada y ligera
FROM python:3.10-slim

# 2. Le decimos a Docker que trabaje dentro de la carpeta /app en el contenedor
WORKDIR /app

# 3. Copiamos el archivo de requerimientos primero (para optimizar la caché de Docker)
COPY requirements.txt .

# 4. Instalamos las dependencias
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copiamos todo el resto de tu código (main.py, schemas.py, etc.)
COPY . .

# 6. Exponemos el puerto por donde habla FastAPI
EXPOSE 8000

# 7. El comando de arranque oficial del servidor
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

# Usamos una imagen ligera de Python optimizada para producción
FROM python:3.10-slim

# Evita que Python escriba archivos .pyc y fuerza a que la consola escupa logs en tiempo real
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Directorio de trabajo dentro del contenedor
WORKDIR /app

# Copiamos solo las dependencias primero (para aprovechar la caché de Docker)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiamos el resto de tu código
COPY . .

# Exponemos el puerto
EXPOSE 10000

# El comando de arranque de tu ERP
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]