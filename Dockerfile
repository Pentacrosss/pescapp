FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=America/Guayaquil

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# init_demo espera a las bases, crea esquema + validador + semilla si
# faltan, y luego arranca gunicorn (1 proceso: la bitácora vive en memoria).
CMD ["sh", "-c", "python manage.py init_demo && exec gunicorn pescapp.wsgi:application --bind 0.0.0.0:8000 --workers 1 --threads 4 --timeout 120"]
