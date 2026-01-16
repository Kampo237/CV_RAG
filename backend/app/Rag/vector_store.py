"""
Vector Store Service - Stockage et recherche vectorielle avec LangChain PGVector

Technos :
- Voyage AI (voyage-3-large, 1024 dimensions)
- PostgreSQL + pgvector
- LangChain PGVector (API >= 0.3, langchain-postgres)
"""

import os
from typing import Optional, List, Dict, Any

from dotenv import load_dotenv
from pydantic import BaseModel
from fastapi import HTTPException
from sqlalchemy.orm import Session
from backend.app.models import Datas


from langchain_core.documents import Document
from langchain_voyageai import VoyageAIEmbeddings

from langchain_postgres import PGVector

load_dotenv()

# =============================================================================
# CONFIGURATION
# =============================================================================

class VectorStoreConfig:
    """Configuration centralisée"""

    VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY", "")
    VOYAGE_MODEL = "voyage-3-large"
    BATCH_SIZE = 32

    DB_USER = os.getenv("DB_USER", "admin")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = os.getenv("DB_PORT", "5432")
    DB_NAME = os.getenv("DB_NAME", "QuizDb")

    COLLECTION_NAME = "cv_knowledge_base"

    @classmethod
    def get_connection_string(cls) -> str:
        """
        IMPORTANT: Utilise psycopg2 (synchrone) - PAS asyncpg
        Pour éviter l'erreur greenlet_spawn
        """
        return f"postgresql+psycopg2://{cls.DB_USER}:{cls.DB_PASSWORD}@{cls.DB_HOST}:{cls.DB_PORT}/{cls.DB_NAME}"


# =============================================================================
# MODELES
# =============================================================================

class EmbeddingRequest(BaseModel):
    message_text: str
    category: str
    metadata: Optional[Dict[str, Any]] = None


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5
    category_filter: Optional[str] = None
    metadata_filter: Optional[Dict[str, Any]] = None


class SearchResult(BaseModel):
    content: str
    category: str
    metadata: dict
    similarity_score: float


# =============================================================================
# SERVICE VECTOR STORE
# =============================================================================

class VectorStoreService:
    """
    Service complet VoyageAI + PGVector (async)
    """

    _instance: Optional["VectorStoreService"] = None

    def __init__(self):
        self._embeddings = None
        self._vector_store = None

    # -------------------------- Singleton --------------------------

    @classmethod
    def get_instance(cls) -> "VectorStoreService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # -------------------------- Embeddings --------------------------

    def _get_embeddings(self) -> VoyageAIEmbeddings:
        if self._embeddings is None:
            self._embeddings = VoyageAIEmbeddings(
                voyage_api_key=VectorStoreConfig.VOYAGE_API_KEY,
                model=VectorStoreConfig.VOYAGE_MODEL,
                batch_size=VectorStoreConfig.BATCH_SIZE,
                truncation=True,
            )
        return self._embeddings

    # -------------------------- Vector Store --------------------------

    def reload_vector_store(self):
        self._vector_store = None
        return self.get_vector_store()

    def get_vector_store(self, collection_name: Optional[str] = None) -> PGVector:
        collection = collection_name or VectorStoreConfig.COLLECTION_NAME

        if self._vector_store is None:
            connection_string = VectorStoreConfig.get_connection_string()

            self._vector_store = PGVector(
                embeddings=self._get_embeddings(),
                collection_name=collection,
                connection=connection_string,  # psycopg2 synchrone
                use_jsonb=True,
            )

            self._vector_store.create_collection()

        return self._vector_store

    # -------------------------- AJOUT DOCUMENTS --------------------------

    async def save_infos(self, requests: List[EmbeddingRequest], db: Session) -> dict:
        """
        Sauvegarde les informations à la fois dans :
        1. Le VectorStore (pour la recherche sémantique)
        2. La table SQL 'Datas' (pour l'affichage et le Text-to-SQL)
        """
        try:
            # 1. Préparation du Vector Store
            vector_store = self.get_vector_store()

            # Listes pour stocker les objets avant sauvegarde
            langchain_documents = []
            sql_datas_entries = []

            for req in requests:
                # --- Préparation pour LangChain (Vector Store) ---
                # On copie les metadata pour ne pas modifier l'original
                meta = (req.metadata or {}).copy()
                meta["category"] = req.category

                langchain_documents.append(
                    Document(
                        page_content=req.message_text,
                        metadata=meta
                    )
                )

                # --- Préparation pour SQL (Table Datas) ---
                # On crée une instance du modèle SQLAlchemy Datas
                new_data = Datas(
                    corpus=req.message_text,
                    category=req.category,
                    extradatas=req.metadata
                )
                sql_datas_entries.append(new_data)

            # 2. Sauvegarde dans le Vector Store (LangChain / pgvector)
            # Cette étape génère les embeddings automatiquement
            ids = vector_store.add_documents(langchain_documents)

            # 3. Sauvegarde dans la table SQL classique (Datas)
            db.add_all(sql_datas_entries)
            db.commit()  # Valide la transaction SQL

            # 4. Rafraichissement (si nécessaire pour ton cache local)
            self.reload_vector_store()

            # Résultat
            created_items = [
                {"id_vector": doc_id, "category": requests[i].category}
                for i, doc_id in enumerate(ids)
            ]

            return {
                "success": True,
                "message": f"{len(created_items)} connaissances ajoutées (Vector + SQL)",
                "results": created_items
            }

        except Exception as e:
            db.rollback()  # Annule les changements SQL en cas d'erreur
            raise HTTPException(
                status_code=500,
                detail=f"Erreur lors de l'ajout hybride: {str(e)}"
            )

    # -------------------------- RECHERCHE --------------------------

    async def search(self, request: SearchRequest) -> List[SearchResult]:
        try:
            vector_store =  self.get_vector_store()

            filter_dict = {}
            if request.category_filter:
                filter_dict["category"] = request.category_filter
            if request.metadata_filter:
                filter_dict.update(request.metadata_filter)

            results = vector_store.similarity_search_with_relevance_scores(
                query=request.query,
                k=request.top_k,
                filter=None if not filter_dict else filter_dict
            )

            final_results = []
            for doc, score in results:
                final_results.append(SearchResult(
                    content=doc.page_content,
                    category=doc.metadata.get("category", "unknown"),
                    metadata=doc.metadata,
                    similarity_score=score,
                ))

            return final_results

        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Erreur de recherche: {str(e)}"
            )

    # -------------------------- RAG simple --------------------------

    async def similarity_search(self, query: str, k: int = 10) -> List[Document]:
        vector_store = self.get_vector_store()
        return vector_store.similarity_search(query, k=k)

    # -------------------------- Retriever --------------------------

    async def as_retriever(self, search_kwargs: Optional[dict] = None):
        vector_store = self.get_vector_store()
        return vector_store.as_retriever(
            search_kwargs=search_kwargs or {"k": 5}
        )


# =============================================================================
# FASTAPI DEPENDENCY
# =============================================================================

def get_vector_store_service() -> VectorStoreService:
    return VectorStoreService.get_instance()


# =============================================================================
# ACCÈS DIRECT (TEST)
# =============================================================================

def get_vector_store() -> PGVector:
    service = VectorStoreService.get_instance()
    return service.get_vector_store()