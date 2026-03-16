FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Dépendances système pour OpenCV et les bibliothèques graphiques
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    curl \
    wget \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pré-télécharger YOLOv8n au moment du build (évite le téléchargement au runtime)
RUN python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')" || echo "YOLO pre-download skipped"

COPY . .

# Créer les répertoires nécessaires
RUN mkdir -p data static/snapshots tests/fixtures

EXPOSE 5000

# Production : gunicorn / Development : flask (voir Makefile)
CMD ["gunicorn", "--config", "gunicorn.conf.py", "app:create_app()"]
