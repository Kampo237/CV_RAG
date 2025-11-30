FROM pgvector/pgvector:pg16

# On copie tes scripts d'initialisation directement DANS l'image
# PostgreSQL exécutera tout ce qui se trouve dans ce dossier au premier démarrage
COPY ./init/ /docker-entrypoint-initdb.d/