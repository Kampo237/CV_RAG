"""
Modèles SQLAlchemy pour le RAG

Architecture à 2 tables:
- datas: Données structurées pour Text-to-SQL (site web + requêtes SQL)
- embeddings: Données vectorielles pour recherche sémantique
"""
from sqlalchemy import Integer, String, Column, JSON, Text, DateTime, func
from app.database import Base


class Datas(Base):
    """
    Table de données structurées - Pour Text-to-SQL et affichage site web

    Utilisée pour:
    - Requêtes SQL précises ("Combien de projets Python?")
    - Affichage sur le site Django
    - Données factuelles (dates, nombres, listes)
    """
    __tablename__ = 'datas'

    id = Column(Integer, primary_key=True, index=True)
    corpus = Column(Text, nullable=False)  # Contenu textuel
    category = Column(String(100), index=True)  # "experience", "competence", "formation", "projet"
    extradatas = Column(JSON, default={})  # Métadonnées structurées
    created_at = Column(DateTime, server_default=func.now())

    # Exemples de extradatas:
    # Pour experience: {"entreprise": "...", "date_debut": "...", "date_fin": "...", "technologies": [...]}
    # Pour competence: {"niveau": 4, "type": "backend"}
    # Pour projet: {"technologies": [...], "url_github": "...", "annee": 2024}

