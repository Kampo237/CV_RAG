"""
Package RAG - Composants du système de Génération Augmentée par Récupération

Composants:
- router: Classification d'intention (SQL / VECTOR / OFF_TOPIC / VECTOR+SQL)
- sql_chain: Génération et exécution de requêtes SQL
- vector_store: Stockage et recherche vectorielle avec PGVector
- retrieval: Reranking des résultats avec Voyage AI
- generation: Chaîne de génération finale avec Claude
- graph: Pipeline LangGraph complet (orchestration automate)
- agent: Pipeline LangGraph agentique (ReAct)
- document_loader: Extraction de texte depuis PDF/DOCX/MD/TXT
- chunking: Découpage sémantique des documents
"""

from .router import get_intent_router
from .sql_chain import get_sql_chain
from .vector_store import VectorStoreService, get_vector_store_service
from .retrieval import rerank_results
from .generation import get_generation_chain, rephrase_question
from .graph import run_rag_graph, get_rag_graph
from .agent import run_rag_agent
from .document_loader import load_document
from .chunking import semantic_chunk

__all__ = [
    'get_intent_router',
    'get_sql_chain',
    'VectorStoreService',
    'get_vector_store_service',
    'rerank_results',
    'get_generation_chain',
    'rephrase_question',
    'run_rag_graph',
    'get_rag_graph',
    'run_rag_agent',
    'load_document',
    'semantic_chunk',
]
