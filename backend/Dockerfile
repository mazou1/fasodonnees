FROM python:3.12-slim

# rsync : utilisé par deploy/backup.sh pour le miroir incrémental des volumes
# Garage. Le mettre ici plutôt que de tirer une image tierce à chaque
# sauvegarde évite une dépendance réseau au milieu de la nuit.
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-fra curl rsync \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv
COPY . .
RUN pip install --no-cache-dir .

ENV PYTHONUNBUFFERED=1
