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
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")

# URL synchrone (pour FastAPI + SQLAlchemy classique)
URL_DATABASE = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# URL asynchrone (pour LangChain PGVector)
URL_DATABASE_ASYNC = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Engine et Session synchrones
engine = create_engine(URL_DATABASE,
                       pool_pre_ping=True,
                       pool_size=5,
                       pool_recycle=300,
                       max_overflow=10,
                       connect_args={
        "sslmode": "require"
    },
                       )
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
