"""
Modèles SQLAlchemy pour le RAG

Architecture à 2 tables:
- datas: Données structurées pour Text-to-SQL (site web + requêtes SQL)
- embeddings: Données vectorielles pour recherche sémantique
"""
from sqlalchemy import Integer, String, Column, JSON, Text, DateTime, func, Boolean
from sqlalchemy.dialects.postgresql import JSONB
from backend.app.database import Base


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


class FAQ(Base):
    """
    Table FAQ - Questions fréquentes pour le portfolio

    Utilisée pour:
    - Affichage sur la page FAQ du site Django
    - Matching des questions utilisateur dans le chatbot
    - Analytics (compteur de vues)
    """
    __tablename__ = 'faq'

    id = Column(Integer, primary_key=True, index=True)
    question = Column(String(500), nullable=False)
    reponse = Column(Text, nullable=False)
    variantes = Column(JSONB, default=[])  # ["Variante 1", "Variante 2", ...]
    categorie = Column(String(50), nullable=False, index=True)
    icone = Column(String(10), default="❓")
    ordre_affichage = Column(Integer, default=0, index=True)
    est_active = Column(Boolean, default=True, index=True)
    vues = Column(Integer, default=0)  # Compteur de vues
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<FAQ {self.id}: {self.question[:50]}...>"

    def to_dict(self):
        """Sérialisation pour l'API"""
        return {
            "id": self.id,
            "question": self.question,
            "reponse": self.reponse,
            "variantes": self.variantes or [],
            "categorie": self.categorie,
            "icone": self.icone,
            "ordre_affichage": self.ordre_affichage,
            "vues": self.vues
        }

    def increment_vues(self, db_session):
        """Incrémente le compteur de vues"""
        self.vues += 1
        db_session.commit()