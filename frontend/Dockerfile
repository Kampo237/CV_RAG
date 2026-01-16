# ==============================================================================
# CV Portfolio Frontend - Dockerfile Django
# ==============================================================================
FROM python:3.11-slim

WORKDIR /app

# Installation des dépendances système
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Installation des dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copie du code source
COPY . .

# Collecte des fichiers statiques
RUN python manage.py collectstatic --noinput 2>/dev/null || true

# Création d'un utilisateur non-root
RUN useradd --create-home appuser \
    && chown -R appuser:appuser /app

USER appuser

# Variables d'environnement
ENV PYTHONUNBUFFERED=1
ENV DJANGO_SETTINGS_MODULE=portfolio_project.settings

# Port exposé
EXPOSE 8000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

# Commande de lancement avec Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "portfolio_project.wsgi:application"]
