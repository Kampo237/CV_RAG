"""
Schémas Pydantic pour la validation des données API
"""
from pydantic import BaseModel, Field, EmailStr, field_validator
from typing import Optional, List, Any
from datetime import datetime


# ==============================================================================
# CHAT SCHEMAS
# ==============================================================================

class ChatRequest(BaseModel):
    """Requête de chat"""
    question: str = Field(..., min_length=1, max_length=1000)
    session_id: Optional[str] = None
    category: Optional[str] = None


class ChatResponse(BaseModel):
    """Réponse de chat (non-streaming)"""
    answer: str
    intent: str
    sources_count: int = 0


class ChatSessionCreate(BaseModel):
    """Création d'une session de chat"""
    email: EmailStr


class ChatSessionResponse(BaseModel):
    """Réponse de session de chat"""
    session_id: str
    email: str
    quota_total: int
    quota_remaining: int
    messages: List[dict] = []


class ChatMessageCreate(BaseModel):
    """Création d'un message de chat"""
    message: str = Field(..., min_length=1, max_length=1000)
    session_id: str


# ==============================================================================
# TESTIMONIAL SCHEMAS
# ==============================================================================

class TestimonialCreate(BaseModel):
    """Création d'un témoignage"""
    author_name: str = Field(..., min_length=2, max_length=100)
    author_email: EmailStr
    author_company: Optional[str] = Field(None, max_length=200)
    author_position: Optional[str] = Field(None, max_length=200)
    content: str = Field(..., min_length=10, max_length=2000)
    rating: int = Field(default=5, ge=1, le=5)


class TestimonialUpdate(BaseModel):
    """Mise à jour d'un témoignage (admin)"""
    is_approved: Optional[bool] = None
    is_featured: Optional[bool] = None


class TestimonialResponse(BaseModel):
    """Réponse témoignage (public)"""
    id: int
    author_name: str
    author_company: Optional[str]
    author_position: Optional[str]
    content: str
    rating: int
    is_featured: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ==============================================================================
# FAQ SCHEMAS
# ==============================================================================

class FAQCreate(BaseModel):
    """Création d'une FAQ"""
    question: str = Field(..., min_length=5, max_length=500)
    reponse: str = Field(..., min_length=10)
    variantes: List[str] = []
    categorie: str = Field(..., min_length=2, max_length=50)
    icone: str = Field(default="❓", max_length=10)
    ordre_affichage: int = Field(default=0, ge=0)


class FAQUpdate(BaseModel):
    """Mise à jour d'une FAQ"""
    question: Optional[str] = Field(None, min_length=5, max_length=500)
    reponse: Optional[str] = Field(None, min_length=10)
    variantes: Optional[List[str]] = None
    categorie: Optional[str] = Field(None, min_length=2, max_length=50)
    icone: Optional[str] = Field(None, max_length=10)
    ordre_affichage: Optional[int] = Field(None, ge=0)
    est_active: Optional[bool] = None


class FAQResponse(BaseModel):
    """Réponse FAQ"""
    id: int
    question: str
    reponse: str
    variantes: List[str]
    categorie: str
    icone: str
    ordre_affichage: int
    vues: int

    class Config:
        from_attributes = True


# ==============================================================================
# KNOWLEDGE BASE SCHEMAS
# ==============================================================================

class KnowledgeAdd(BaseModel):
    """Ajout de connaissance au vector store"""
    message_text: str = Field(..., min_length=10)
    category: str = Field(..., min_length=2, max_length=100)
    metadata: dict = Field(default_factory=dict)


class KnowledgeResponse(BaseModel):
    """Réponse d'ajout de connaissance"""
    success: bool
    message: str
    ids: List[str] = []


# ==============================================================================
# PROJECT SCHEMAS (pour l'API)
# ==============================================================================

class ProjectResponse(BaseModel):
    """Réponse projet"""
    id: int
    corpus: str
    category: str
    extradatas: dict
    created_at: Optional[datetime]

    class Config:
        from_attributes = True


# ==============================================================================
# STATS SCHEMAS
# ==============================================================================

class StatsResponse(BaseModel):
    """Statistiques de la base de données"""
    total_datas: int
    total_embeddings: int
    total_faq: int
    total_testimonials: int
    total_chat_sessions: int
    categories: dict
