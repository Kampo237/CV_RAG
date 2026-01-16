"""
Package RAG - Composants du système de Génération Augmentée par Récupération

Composants:
- router: Classification d'intention (SQL / VECTOR / OFF_TOPIC / VECTOR+SQL)
- sql_chain: Génération et exécution de requêtes SQL
- vector_store: Stockage et recherche vectorielle avec PGVector
- retrieval: Reranking des résultats avec Voyage AI
- generation: Chaîne de génération finale avec Claude
"""

from .router import get_intent_router
from .sql_chain import get_sql_chain
from .vector_store import VectorStoreService, get_vector_store_service
from .retrieval import rerank_results
from .generation import get_generation_chain, rephrase_question

__all__ = [
    'get_intent_router',
    'get_sql_chain',
    'VectorStoreService',
    'get_vector_store_service',
    'rerank_results',
    'get_generation_chain',
    'rephrase_question'
]
