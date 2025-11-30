FROM python:3.11-slim

WORKDIR /code

# Installation des dépendances système
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Installation des dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copie de tout le dossier 'app' vers le conteneur
COPY ./app ./app
COPY ./.chainlit ./.chainlit
COPY ./.env ./.env

# Création d'un utilisateur non-root pour la sécurité
RUN useradd --create-home appuser \
    && mkdir -p /code/.files \
    && chown -R appuser:appuser /code

USER appuser


ENV PYTHONPATH=/code
# Commande de lancement (Note le app.main:app car c'est dans le dossier app)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]