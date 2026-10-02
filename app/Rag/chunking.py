"""
Chunking Sémantique — Découpage intelligent de documents.

Contrairement au chunking par taille fixe (qui coupe tous les N caractères
au mépris du sens), le SemanticChunker utilise les embeddings pour détecter
les changements de sujet et coupe aux frontières naturelles.

Comment ça marche en interne :
1. Découpe le texte en phrases
2. Génère un embedding pour chaque phrase (via Voyage AI)
3. Calcule la distance cosinus entre phrases consécutives
4. Coupe quand la distance dépasse un seuil (= changement de sujet détecté)

Coût : un appel d'embedding par phrase. Pour un PDF de 50 pages, compte
~500-1000 appels embeddings (heureusement Voyage AI est très rapide).
"""

import os
import logging
from typing import List, Optional

from langchain_voyageai import VoyageAIEmbeddings
from langchain_experimental.text_splitter import SemanticChunker

logger = logging.getLogger("rag_pipeline")


# =============================================================================
# SINGLETON EMBEDDINGS
# =============================================================================

_embeddings: Optional[VoyageAIEmbeddings] = None


def _get_embeddings() -> VoyageAIEmbeddings:
    """
    Réutilise la même instance d'embeddings que le vector store
    pour éviter de recréer un client à chaque chunk.
    """
    global _embeddings
    if _embeddings is None:
        _embeddings = VoyageAIEmbeddings(
            voyage_api_key=os.getenv("VOYAGE_API_KEY"),
            model="voyage-3-large",
            batch_size=32,
            truncation=True,
        )
    return _embeddings


# =============================================================================
# CHUNKER SÉMANTIQUE
# =============================================================================

_chunker: Optional[SemanticChunker] = None


def _get_chunker() -> SemanticChunker:
    """
    Construit le SemanticChunker avec un seuil de découpe optimisé.

    breakpoint_threshold_type :
      - "percentile" (défaut)        : coupe aux endroits où la distance entre
                                       phrases dépasse le 95e percentile.
                                       Bon équilibre, recommandé.
      - "standard_deviation"         : coupe à N écarts-types au-dessus de la moyenne.
      - "interquartile"              : coupe au-delà de l'IQR (plus agressif).
      - "gradient"                   : détecte les ruptures par dérivée.

    breakpoint_threshold_amount :
      - Plus haut = chunks plus longs (moins de coupes)
      - Plus bas  = chunks plus courts (plus de coupes)
      - 95 (défaut percentile) est un bon point de départ
    """
    global _chunker
    if _chunker is None:
        _chunker = SemanticChunker(
            embeddings=_get_embeddings(),
            breakpoint_threshold_type="percentile",
            breakpoint_threshold_amount=95.0,
        )
        logger.info("[chunking] SemanticChunker initialisé (percentile=95)")
    return _chunker


# =============================================================================
# API PUBLIQUE
# =============================================================================

def semantic_chunk(text: str, min_chunk_size: int = 100) -> List[str]:
    """
    Découpe un texte en chunks sémantiquement cohérents.

    Args:
        text : le texte complet à découper
        min_chunk_size : taille minimum d'un chunk (caractères).
                         Les chunks plus petits sont fusionnés avec le suivant.

    Returns:
        Liste de chunks (chaînes de caractères)
    """
    chunker = _get_chunker()
    raw_chunks = chunker.split_text(text)

    # Fusionner les chunks trop petits avec leur voisin
    # (un chunk de 30 caractères n'a aucune valeur sémantique pour le retrieval)
    merged_chunks = []
    buffer = ""

    for chunk in raw_chunks:
        if len(buffer) + len(chunk) < min_chunk_size:
            buffer += "\n\n" + chunk if buffer else chunk
        else:
            if buffer:
                merged_chunks.append(buffer + "\n\n" + chunk)
                buffer = ""
            else:
                merged_chunks.append(chunk)

    if buffer:
        # Dernier buffer trop petit : on le rattache au chunk précédent s'il existe
        if merged_chunks:
            merged_chunks[-1] += "\n\n" + buffer
        else:
            merged_chunks.append(buffer)

    logger.info(
        f"[semantic_chunk] {len(text)} caractères → "
        f"{len(raw_chunks)} chunks bruts → "
        f"{len(merged_chunks)} chunks fusionnés"
    )

    return merged_chunks
