"""
Document Loader — Extraction du texte brut depuis différents formats.

Formats supportés :
  - PDF (.pdf)        → pypdf
  - Word (.docx)      → python-docx
  - Markdown (.md)    → lecture directe (le markdown est du texte structuré)
  - Texte brut (.txt) → lecture directe

Chaque loader retourne une chaîne de texte unique, prête pour le chunking.
"""

import logging
from io import BytesIO
from pathlib import Path

logger = logging.getLogger("rag_pipeline")


# =============================================================================
# LOADERS PAR FORMAT
# =============================================================================

def load_pdf(file_bytes: bytes) -> str:
    """
    Extrait le texte d'un PDF.

    Note : pypdf gère les PDF avec texte sélectionnable. Pour les PDF scannés
    (images), il faudrait un OCR comme pytesseract — pas géré ici.
    """
    from pypdf import PdfReader

    reader = PdfReader(BytesIO(file_bytes))
    pages_text = []

    for i, page in enumerate(reader.pages):
        try:
            text = page.extract_text() or ""
            if text.strip():
                pages_text.append(text)
        except Exception as e:
            logger.warning(f"[load_pdf] Erreur page {i}: {e}")

    full_text = "\n\n".join(pages_text)
    logger.info(f"[load_pdf] {len(reader.pages)} pages → {len(full_text)} caractères")
    return full_text


def load_docx(file_bytes: bytes) -> str:
    """
    Extrait le texte d'un fichier Word.

    Note : ne récupère que le texte des paragraphes. Les tableaux, en-têtes
    et pieds de page sont ignorés pour rester simple.
    """
    from docx import Document as DocxDocument

    doc = DocxDocument(BytesIO(file_bytes))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]

    # Aussi récupérer le texte des tableaux (souvent important dans un CV ou rapport)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                if cell.text.strip():
                    paragraphs.append(cell.text)

    full_text = "\n\n".join(paragraphs)
    logger.info(f"[load_docx] {len(paragraphs)} paragraphes → {len(full_text)} caractères")
    return full_text


def load_text(file_bytes: bytes) -> str:
    """
    Lit un fichier texte brut ou markdown (UTF-8).

    Le markdown est traité comme du texte — le SemanticChunker
    respectera naturellement les sauts de ligne et titres.
    """
    text = file_bytes.decode("utf-8", errors="replace")
    logger.info(f"[load_text] {len(text)} caractères")
    return text


# =============================================================================
# DISPATCHER PRINCIPAL
# =============================================================================

# Mapping extension → fonction de chargement
LOADERS = {
    ".pdf": load_pdf,
    ".docx": load_docx,
    ".md": load_text,
    ".txt": load_text,
    ".markdown": load_text,
}


def load_document(filename: str, file_bytes: bytes) -> str:
    """
    Charge un document selon son extension.

    Args:
        filename : nom du fichier (sert à déterminer le format via l'extension)
        file_bytes : contenu binaire du fichier

    Returns:
        Texte brut extrait du document

    Raises:
        ValueError : si l'extension n'est pas supportée
    """
    extension = Path(filename).suffix.lower()

    if extension not in LOADERS:
        supported = ", ".join(LOADERS.keys())
        raise ValueError(
            f"Format '{extension}' non supporté. Formats acceptés : {supported}"
        )

    loader = LOADERS[extension]
    text = loader(file_bytes)

    if not text or not text.strip():
        raise ValueError(f"Le document {filename} ne contient pas de texte extractible.")

    return text
