"""
Modèles SQLAlchemy pour le RAG

Architecture des tables:
- datas: Données structurées pour Text-to-SQL (site web + requêtes SQL)
- faq: Questions fréquentes
- testimonials: Témoignages/commentaires des visiteurs
- chat_sessions: Sessions de conversation du chatbot
"""
from sqlalchemy import Integer, String, Column, JSON, Text, DateTime, func, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

try:
    from app.database import Base
except ImportError:
    from database import Base


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
    corpus = Column(Text, nullable=False)
    category = Column(String(100), index=True)
    extradatas = Column(JSON, default={})
    created_at = Column(DateTime, server_default=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "corpus": self.corpus,
            "category": self.category,
            "extradatas": self.extradatas or {},
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


class FAQ(Base):
    """
    Table FAQ - Questions fréquentes pour le portfolio
    """
    __tablename__ = 'faq'

    id = Column(Integer, primary_key=True, index=True)
    question = Column(String(500), nullable=False)
    reponse = Column(Text, nullable=False)
    variantes = Column(JSONB, default=[])
    categorie = Column(String(50), nullable=False, index=True)
    icone = Column(String(10), default="❓")
    ordre_affichage = Column(Integer, default=0, index=True)
    est_active = Column(Boolean, default=True, index=True)
    vues = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<FAQ {self.id}: {self.question[:50]}...>"

    def to_dict(self):
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
        self.vues += 1
        db_session.commit()


class Testimonial(Base):
    """
    Table des témoignages/commentaires des visiteurs

    Utilisée pour:
    - Collecter les retours des recruteurs/visiteurs
    - Affichage sur la page témoignages
    - Modération avant publication
    """
    __tablename__ = 'testimonials'

    id = Column(Integer, primary_key=True, index=True)
    author_name = Column(String(100), nullable=False)
    author_email = Column(String(255), nullable=False, index=True)
    author_company = Column(String(200), nullable=True)
    author_position = Column(String(200), nullable=True)
    content = Column(Text, nullable=False)
    rating = Column(Integer, default=5)  # Note de 1 à 5
    is_approved = Column(Boolean, default=False, index=True)
    is_featured = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<Testimonial {self.id}: {self.author_name}>"

    def to_dict(self, include_email=False):
        data = {
            "id": self.id,
            "author_name": self.author_name,
            "author_company": self.author_company,
            "author_position": self.author_position,
            "content": self.content,
            "rating": self.rating,
            "is_featured": self.is_featured,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
        if include_email:
            data["author_email"] = self.author_email
            data["is_approved"] = self.is_approved
        return data


class ChatSession(Base):
    """
    Table des sessions de chat

    Utilisée pour:
    - Authentification légère des utilisateurs du chatbot
    - Gestion des quotas de messages
    - Persistance de l'historique de conversation
    """
    __tablename__ = 'chat_sessions'

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), nullable=False, index=True)
    quota_total = Column(Integer, default=50)
    quota_used = Column(Integer, default=0)
    is_active = Column(Boolean, default=True, index=True)
    last_activity = Column(DateTime, server_default=func.now(), onupdate=func.now())
    created_at = Column(DateTime, server_default=func.now())

    # Relation avec les messages
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<ChatSession {self.session_id}: {self.email}>"

    @property
    def quota_remaining(self):
        return max(0, self.quota_total - self.quota_used)

    def to_dict(self, include_messages=False):
        data = {
            "session_id": self.session_id,
            "email": self.email,
            "quota_total": self.quota_total,
            "quota_remaining": self.quota_remaining,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
        if include_messages:
            data["messages"] = [msg.to_dict() for msg in self.messages[-20:]]  # Last 20 messages
        return data


class ChatMessage(Base):
    """
    Table des messages de chat

    Stocke l'historique des conversations pour chaque session
    """
    __tablename__ = 'chat_messages'

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey('chat_sessions.id', ondelete='CASCADE'), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # 'user' ou 'assistant'
    content = Column(Text, nullable=False)
    intent = Column(String(20), nullable=True)  # SQL, VECTOR, VECTOR_SQL, OFF_TOPIC
    metadata = Column(JSON, default={})
    created_at = Column(DateTime, server_default=func.now())

    # Relation avec la session
    session = relationship("ChatSession", back_populates="messages")

    def __repr__(self):
        return f"<ChatMessage {self.id}: {self.role}>"

    def to_dict(self):
        return {
            "role": self.role,
            "content": self.content,
            "intent": self.intent,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
