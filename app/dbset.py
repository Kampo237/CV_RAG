import asyncio
from dotenv import load_dotenv

from sqlalchemy import text
from app.database import SessionLocal
from langchain_core.documents import Document
from app.Rag.vector_store import get_vector_store

load_dotenv()

async def migrate_embeddings_to_langchain():
    session = SessionLocal()

    print("📥 Lecture des données existantes...")

    rows = session.execute(
        text("SELECT id, corpus, category, extradatas FROM embeddings")
    ).fetchall()

    if not rows:
        print("⚠️ Aucune donnée trouvée dans la table 'embeddings'.")
        return

    print(f"✔ {len(rows)} lignes trouvées.")

    vector_store = get_vector_store()

    docs = []

    for row in rows:
        doc = Document(
            page_content=row.corpus,  # contenu texte
            metadata={
                "db_id": row.id,
                "category": row.category ,
                "extradatas": row.extradatas,
            }
        )
        docs.append(doc)

    print("📤 Migration vers LangChain PGVector...")
    vector_store.add_documents(docs)

    print("🎉 Migration terminée avec succès !")


if __name__ == "__main__":
    asyncio.run(migrate_embeddings_to_langchain())
