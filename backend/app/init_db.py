"""
Script d'initialisation de la base de données

Usage:
    python -m app.init_db

Ou depuis Docker:
    docker exec cv-chatbot-api python -m app.init_db
"""
import os
import sys
from dotenv import load_dotenv

load_dotenv()

# Ajouter le dossier parent au path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.database import engine, Base
from app.models import Datas, FAQ, Testimonial, ChatSession, ChatMessage


def init_database():
    """Initialise la base de données avec toutes les tables"""
    print("=" * 60)
    print("INITIALISATION DE LA BASE DE DONNÉES")
    print("=" * 60)

    try:
        # Créer l'extension pgvector si elle n'existe pas
        with engine.connect() as conn:
            print("\n[1/4] Vérification de l'extension pgvector...")
            try:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                conn.commit()
                print("      Extension pgvector OK")
            except Exception as e:
                print(f"      Note: pgvector - {e}")

        # Créer toutes les tables
        print("\n[2/4] Création des tables...")
        Base.metadata.create_all(bind=engine)
        print("      Tables créées avec succès:")
        for table in Base.metadata.sorted_tables:
            print(f"        - {table.name}")

        # Vérifier les tables
        print("\n[3/4] Vérification des tables...")
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name
            """))
            tables = [row[0] for row in result]
            print(f"      Tables existantes: {len(tables)}")
            for t in tables:
                print(f"        - {t}")

        # Stats
        print("\n[4/4] Statistiques...")
        with engine.connect() as conn:
            for table_name in ['datas', 'faq', 'testimonials', 'chat_sessions', 'chat_messages']:
                try:
                    result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                    count = result.scalar()
                    print(f"      {table_name}: {count} enregistrements")
                except Exception:
                    print(f"      {table_name}: (table non trouvée)")

        print("\n" + "=" * 60)
        print("INITIALISATION TERMINÉE AVEC SUCCÈS")
        print("=" * 60)
        return True

    except Exception as e:
        print(f"\nERREUR: {e}")
        import traceback
        traceback.print_exc()
        return False


def create_sample_data():
    """Crée quelques données d'exemple"""
    from sqlalchemy.orm import Session as DBSession

    print("\nCréation de données d'exemple...")

    with DBSession(engine) as session:
        # Vérifier si des données existent déjà
        if session.query(FAQ).count() > 0:
            print("  Des FAQ existent déjà, skip...")
        else:
            # Créer quelques FAQ
            faqs = [
                FAQ(
                    question="Qui est Jordan ?",
                    reponse="Jordan est un étudiant en informatique au Cégep de Chicoutimi, passionné par le développement web et l'IA.",
                    categorie="general",
                    icone="?",
                    ordre_affichage=1
                ),
                FAQ(
                    question="Quelles sont ses compétences ?",
                    reponse="Python, C#, .NET, Django, FastAPI, PostgreSQL, Docker, AWS, LangChain, et plus encore.",
                    categorie="competences",
                    icone="?",
                    ordre_affichage=2
                ),
                FAQ(
                    question="Comment le contacter ?",
                    reponse="Vous pouvez contacter Jordan par email à kampojordan237@gmail.com",
                    categorie="contact",
                    icone="?",
                    ordre_affichage=3
                ),
            ]
            session.add_all(faqs)
            session.commit()
            print(f"  {len(faqs)} FAQ créées")

    print("Données d'exemple créées!")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Initialisation de la base de données")
    parser.add_argument("--sample", action="store_true", help="Créer des données d'exemple")
    args = parser.parse_args()

    success = init_database()

    if success and args.sample:
        create_sample_data()

    sys.exit(0 if success else 1)
