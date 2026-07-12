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