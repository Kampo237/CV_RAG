"""
Configuration de la base de données PostgreSQL
Support synchrone (SQLAlchemy) et asynchrone (asyncpg pour LangChain)
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os
from dotenv import load_dotenv

load_dotenv()

# Configuration centralisée
DB_USER = os.getenv("DB_USER", "admin")
DB_PASSWORD = os.getenv("DB_PASSWORD", "Admin123")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "QuizDb")

# URL synchrone (pour FastAPI + SQLAlchemy classique)
URL_DATABASE = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# URL asynchrone (pour LangChain PGVector)
URL_DATABASE_ASYNC = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Engine et Session synchrones
engine = create_engine(URL_DATABASE)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base pour les modèles
Base = declarative_base()


def get_db():
    """Dépendance FastAPI pour injection de session DB"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
