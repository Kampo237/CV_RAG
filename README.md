# CV RAG Portfolio - Chatbot Intelligent

Portfolio professionnel avec chatbot RAG (Retrieval Augmented Generation) pour Yann Willy Jordan Pokam Teguia.

## Architecture

```
CV_RAG/
├── backend/                # FastAPI RAG API (Port 8001)
│   ├── app/
│   │   ├── main.py        # Application principale
│   │   ├── models.py      # Modèles SQLAlchemy
│   │   ├── database.py    # Configuration DB
│   │   └── Rag/           # Pipeline RAG
│   ├── Dockerfile
│   └── requirements.txt
│
├── frontend/               # Django Portfolio (Port 8000)
│   ├── portfolio_app/     # Application principale
│   ├── static/            # CSS, JS
│   ├── Dockerfile
│   └── requirements.txt
│
├── docker-compose.yml     # Orchestration
└── .env.example           # Template variables
```

## Technologies

- **Backend**: FastAPI, LangChain, Claude AI, Voyage AI, PostgreSQL + pgvector
- **Frontend**: Django 5.x, Bootstrap, JavaScript
- **Infrastructure**: Docker, AWS (RDS, EC2)

## Démarrage rapide

### 1. Configuration

```bash
# Cloner le repo
git clone <repo-url>
cd CV_RAG

# Copier et configurer les variables d'environnement
cp .env.example .env
# Éditer .env avec vos credentials
```

### 2. Variables d'environnement requises

```env
# Base de données
DB_HOST=your-rds-host.rds.amazonaws.com
DB_PORT=5432
DB_NAME=cvdb
DB_USER=postgres
DB_PASSWORD=your_password

# APIs IA
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
VOYAGE_API_KEY=pa-...

# Django
DJANGO_SECRET_KEY=your-secret-key
DJANGO_DEBUG=False
```

### 3. Lancement avec Docker

```bash
# Build et démarrage
docker-compose up --build -d

# Vérifier les logs
docker-compose logs -f

# Initialiser la base de données
docker exec cv-chatbot-api python -m app.init_db
```

### 4. Accès

- **Frontend**: http://localhost:8000
- **API Backend**: http://localhost:8001
- **API Docs**: http://localhost:8001/docs

## Endpoints API principaux

| Endpoint | Méthode | Description |
|----------|---------|-------------|
| `/` | GET | Health check |
| `/chat/` | POST | Chat RAG (streaming) |
| `/api/chat/session` | POST | Créer session |
| `/api/chat/message` | POST | Envoyer message |
| `/api/testimonials/` | GET/POST | Témoignages |
| `/api/projects` | GET | Liste projets |
| `/api/skills` | GET | Compétences |
| `/faq/` | GET | FAQ |
| `/stats/` | GET | Statistiques |

## Développement local

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8001
```

### Frontend

```bash
cd frontend
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 8000
```

## Migrations Django

```bash
cd frontend
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
```

## Structure de la base de données

### Tables principales

- `datas` - Données structurées (projets, compétences, etc.)
- `faq` - Questions fréquentes
- `testimonials` - Témoignages
- `chat_sessions` - Sessions de chat
- `chat_messages` - Messages de chat
- `langchain_pg_embedding` - Embeddings vectoriels

## Pipeline RAG

1. **Rate Limiting** - Max 50 requêtes/session
2. **Historique** - Conservation des 20 derniers messages
3. **Reformulation** - Question autonome via GPT-4
4. **Routage** - Classification SQL/VECTOR/VECTOR_SQL/OFF_TOPIC
5. **Récupération** - SQL ou recherche vectorielle + reranking
6. **Génération** - Réponse via Claude avec streaming

## Déploiement AWS

1. Créer une instance EC2 (t3.small minimum)
2. Créer une base RDS PostgreSQL avec pgvector
3. Configurer les security groups
4. Déployer avec Docker Compose

## Auteur

**Yann Willy Jordan Pokam Teguia**
- Email: kampojordan237@gmail.com
- GitHub: [Kampo237](https://github.com/Kampo237)

## Licence

MIT License
