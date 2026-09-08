"""
Modèles SQLAlchemy pour le RAG

Architecture à 2 tables:
- datas: Données structurées pour Text-to-SQL (site web + requêtes SQL)
- embeddings: Données vectorielles pour recherche sémantique
"""
from sqlalchemy import Integer, String, Column, JSON, Text, DateTime, func, Boolean
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
    extradatas = Column(JSON, default=dict)  # Métadonnées structurées
    created_at = Column(DateTime, server_default=func.now())

    # Exemples de extradatas:
    # Pour experience: {"entreprise": "...", "date_debut": "...", "date_fin": "...", "technologies": [...]}
    # Pour competence: {"niveau": 4, "type": "backend"}
    # Pour projet: {"technologies": [...], "url_github": "...", "annee": 2024}


class Testimonial(Base):
    __tablename__ = "testimonials"

    id = Column(Integer, primary_key=True, index=True)
    rating = Column(Integer, nullable=False)
    is_approved = Column(Boolean, default=False)
    is_featured = Column(Boolean, default=False)

    # Gestion automatique des dates
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    author_name = Column(String, nullable=False)
    author_email = Column(String, nullable=False)
    author_company = Column(String, nullable=True)
    author_position = Column(String, nullable=True)
    content = Column(Text, nullable=False)


class ChatSession(Base):
    """
    Historique de conversation persistant.

    Chaque session correspond à un visiteur unique (identifié par session_id
    stocké dans son localStorage). Les messages sont stockés en JSON pour
    être injectés directement dans le contexte du LLM.

    Colonnes :
      - session_id  : UUID généré côté frontend (localStorage)
      - messages    : [{"role": "user"|"assistant", "content": "..."}]
      - message_count : compteur rapide sans parser le JSON
      - created_at  : première interaction
      - updated_at  : dernière interaction (pour le nettoyage)
    """
    __tablename__ = "chat_sessions"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(100), unique=True, nullable=False, index=True)
    messages = Column(JSON, default=list)
    message_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())