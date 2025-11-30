"""
Module de Reranking - Réordonnancement des résultats avec Voyage AI

Le reranking améliore la précision de la recherche vectorielle:
1. La recherche vectorielle (Bi-Encoder) récupère un large ensemble de candidats (rappel)
2. Le reranker (Cross-Encoder) réévalue chaque candidat avec précision

Modèle utilisé: rerank-2 de Voyage AI
"""
import os
from typing import List, Optional
from langchain_core.documents import Document
import voyageai
from dotenv import load_dotenv

# Import optionnel de langsmith pour le tracing
try:
    from langsmith import traceable
    LANGSMITH_AVAILABLE = True
except ImportError:
    LANGSMITH_AVAILABLE = False
    # Décorateur factice si langsmith n'est pas installé
    def traceable(*args, **kwargs):
        def decorator(func):
            return func
        return decorator

load_dotenv()

# Client Voyage AI
_voyage_client: Optional[voyageai.Client] = None


def get_voyage_client() -> voyageai.Client:
    """Singleton pour le client Voyage AI"""
    global _voyage_client
    if _voyage_client is None:
        api_key = os.getenv("VOYAGE_API_KEY")
        if not api_key:
            raise ValueError("VOYAGE_API_KEY non définie dans .env")
        _voyage_client = voyageai.Client(api_key=api_key)
    return _voyage_client


@traceable(name="VoyageAI_Rerank")
def rerank_results(
    query: str,
    documents: List[Document],
    top_k: int = 3,
    model: str = "rerank-2"
) -> List[Document]:
    """
    Réordonne les documents par pertinence avec Voyage AI Reranker

    Pipeline:
    1. Extraction du contenu textuel des documents
    2. Appel API Voyage AI rerank
    3. Reconstruction des Documents triés par score

    Args:
        query: Question de l'utilisateur
        documents: Liste de Documents issus de la recherche vectorielle
        top_k: Nombre de documents à retourner (défaut: 3)
        model: Modèle de reranking ("rerank-2" ou "rerank-2-lite")

    Returns:
        Liste des top_k Documents les plus pertinents, triés par score décroissant

    Example:
#        >>> raw_docs = await vector_store.similarity_search(query, k=10)
#        >>> refined_docs = rerank_results(query, raw_docs, top_k=3)
#        >>> context = "\\n".join([d.page_content for d in refined_docs])
    """
    # Cas limite: pas de documents
    if not documents:
        return []

    # Cas limite: moins de documents que demandé
    if len(documents) <= top_k:
        return documents

    try:
        client = get_voyage_client()

        # Extraction des contenus textuels
        docs_content = [doc.page_content for doc in documents]

        # Appel API Rerank
        reranking_response = client.rerank(
            query=query,
            documents=docs_content,
            model=model,
            top_k=top_k
        )

        # Reconstruction des Documents triés
        final_docs = []
        for result in reranking_response.results:
            original_doc = documents[result.index]

            # Ajout du score de pertinence dans les métadonnées
            original_doc.metadata["relevance_score"] = result.relevance_score
            original_doc.metadata["rerank_index"] = result.index

            final_docs.append(original_doc)

        return final_docs

    except Exception as e:
        # En cas d'erreur, retourner les premiers documents non rerankés
        print(f"Erreur reranking: {e}. Fallback sur les premiers documents.")
        return documents[:top_k]


async def rerank_results_async(
    query: str,
    documents: List[Document],
    top_k: int = 3,
    model: str = "rerank-2"
) -> List[Document]:
    """
    Version asynchrone du reranking

    Note: Le client Voyage AI est synchrone, donc on wrappe l'appel.
    Pour de meilleures performances en production, considérer asyncio.to_thread()
    """
    import asyncio

    # Exécuter le reranking synchrone dans un thread pool
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        lambda: rerank_results(query, documents, top_k, model)
    )


def format_context(documents: List[Document], separator: str = "\n\n---\n\n") -> str:
    """
    Formate une liste de Documents en contexte textuel pour le LLM

    Args:
        documents: Liste de Documents
        separator: Séparateur entre les documents

    Returns:
        Contexte formaté prêt pour injection dans le prompt
    """
    if not documents:
        return "Aucune information pertinente trouvée."

    formatted_parts = []
    for i, doc in enumerate(documents, 1):
        category = doc.metadata.get("category", "Général")
        score = doc.metadata.get("relevance_score", "N/A")

        part = f"[Source {i} - {category}]\n{doc.page_content}"
        if score != "N/A":
            part += f"\n(Pertinence: {score:.2f})"

        formatted_parts.append(part)

    return separator.join(formatted_parts)


# =============================================================================
# FONCTION COMBINÉE: RECHERCHE + RERANK
# =============================================================================

@traceable(name="RetrieveAndRerank_Pipeline")
async def retrieve_and_rerank(
    query: str,
    vector_store_service,
    initial_k: int = 10,
    final_k: int = 3
) -> List[Document]:
    """
    Pipeline complet: Recherche vectorielle + Reranking
    
    Args:
        query: Question de l'utilisateur
        vector_store_service: Instance de VectorStoreService
        initial_k: Nombre de documents à récupérer initialement
        final_k: Nombre de documents après reranking
    
    Returns:
        Liste des documents les plus pertinents
    """
    # Étape 1: Recherche vectorielle large (rappel)
    raw_docs = await vector_store_service.similarity_search(query, k=initial_k)
    
    # Étape 2: Reranking pour précision
    refined_docs = await rerank_results_async(query, raw_docs, top_k=final_k)
    
    return refined_docs
