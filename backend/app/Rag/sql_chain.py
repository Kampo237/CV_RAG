"""
Chaîne Text-to-SQL - Génération et exécution de requêtes SQL

IMPORTANT:
- Utilise la table 'embeddings' (votre table) pour les requêtes structurées
- La table 'langchain_pg_embedding' est pour le vector store, pas pour SQL
- Inclut un parsing pour extraire uniquement la requête SQL
"""
from langchain_community.utilities import SQLDatabase
from langchain_community.tools import QuerySQLDatabaseTool
from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough, RunnableLambda
from dotenv import load_dotenv
import os
import re
import logging

load_dotenv()

logger = logging.getLogger("rag_pipeline")

# URL de connexion
DB_URL = os.getenv("DATABASE_URL", "postgresql://cv_reader:user@localhost:5432/QuizDb")

# Table à utiliser pour les requêtes SQL
# Utiliser 'embeddings' (votre table avec corpus, category, extradatas)
# PAS 'langchain_pg_embedding' qui est pour le vector store
SQL_TABLE = "datas,langchain_pg_embedding"


def extract_sql_query(text: str) -> str:
    """
    Extrait uniquement la requête SQL de la sortie du LLM

    Le LLM peut générer:
    - "Question: ... SQLQuery: SELECT ..."
    - "SQLQuery: SELECT ..."
    - "SELECT ..."
    - "```sql SELECT ... ```"

    Cette fonction extrait uniquement le SELECT.
    """
    if not text:
        return ""

    # Nettoyer les espaces
    text = text.strip()

    # Pattern 1: SQLQuery: SELECT ...
    match = re.search(r'SQLQuery:\s*(SELECT.+?)(?:;|$)', text, re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip() + ";"

    # Pattern 2: ```sql ... ```
    match = re.search(r'```sql\s*(SELECT.+?)\s*```', text, re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()

    # Pattern 3: SELECT ... directement
    match = re.search(r'(SELECT.+?)(?:;|$)', text, re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip() + ";"

    # Si rien ne correspond, retourner le texte original (va probablement échouer)
    logger.warning(f"Impossible d'extraire SQL de: {text[:100]}...")
    return text


def get_sql_chain():
    """
    Crée la chaîne Text-to-SQL complète avec parsing amélioré

    Pipeline:
    1. Question → Génération SQL (Claude)
    2. Extraction de la requête SQL pure
    3. SQL → Exécution (PostgreSQL)
    4. Résultat → Formatage réponse

    Returns:
        Chaîne LangChain exécutable
    """
    llm = ChatAnthropic(
        model_name="claude-haiku-4-5-20251001",
        temperature=0,
        api_key=os.getenv("ANTHROPIC_API_KEY")
    )

    # Connexion à la base de données
    db = SQLDatabase.from_uri(
        DB_URL,
        include_tables=[SQL_TABLE],
        sample_rows_in_table_info=3
    )

    # Prompt personnalisé pour générer du SQL propre
    sql_prompt = ChatPromptTemplate.from_messages([
        ("system", """Tu es un expert SQL qui génère des requêtes PostgreSQL.

Table disponible: {table_info}

RÈGLES IMPORTANTES:
1. Génère UNIQUEMENT la requête SQL, rien d'autre
2. Pas de "Question:", pas de "SQLQuery:", juste le SELECT
3. Utilise des guillemets doubles pour les noms de colonnes si nécessaire
4. La colonne 'corpus' contient le texte descriptif
5. La colonne 'category' contient le type (experience, competence, formation, projet, etc.)
6. La colonne 'extradatas' est un JSON avec des métadonnées supplémentaires
7. Pour chercher du texte, utilise ILIKE avec %mot%
8. Limite toujours à 10 résultats maximum

Exemples:
- "Combien de projets?" → SELECT COUNT(*) FROM datas WHERE category = 'projet';
- "Liste les compétences" → SELECT corpus, category FROM langcain_pg_embedding WHERE category = 'competence' LIMIT 10;
- "Expérience en Python" → SELECT corpus, extradatas FROM datas WHERE corpus ILIKE '%Python%' LIMIT 10;
"""),
        ("human", "Question: {question}\n\nSQL:")
    ])

    # Chaîne de génération SQL
    def generate_sql(inputs):
        table_info = db.get_table_info()
        prompt_value = sql_prompt.format(
            table_info=table_info,
            question=inputs["question"]
        )
        response = llm.invoke(prompt_value)
        raw_sql = response.content
        # Extraire uniquement le SQL
        clean_sql = extract_sql_query(raw_sql)
        logger.debug(f"SQL brut: {raw_sql[:100]}...")
        logger.debug(f"SQL extrait: {clean_sql}")
        return clean_sql

    # Outil d'exécution SQL
    execute_query = QuerySQLDatabaseTool(db=db)

    # Fonction d'exécution avec gestion d'erreur
    def execute_sql(sql: str) -> str:
        try:
            if not sql or not sql.strip().upper().startswith("SELECT"):
                return "ERREUR: Requête SQL invalide"
            result = execute_query.invoke(sql)
            return result if result else "Aucun résultat trouvé"
        except Exception as e:
            logger.error(f"Erreur SQL: {e}")
            return f"ERREUR_SQL: {str(e)}"

    # Chaîne de formatage de la réponse
    answer_prompt = ChatPromptTemplate.from_messages([
        ("system", """Tu es un assistant qui répond aux questions sur le CV de Yann.

Utilise le résultat de la requête SQL pour formuler une réponse naturelle et professionnelle.

RÈGLES:
- Si le résultat commence par "ERREUR", indique qu'il y a eu un problème technique
- Si le résultat est vide ou "Aucun résultat", dis que tu n'as pas trouvé l'information
- Ne mentionne JAMAIS la requête SQL ou les détails techniques
- Formule une réponse conversationnelle et utile"""),
        ("human", """Question: {question}

Résultat de la recherche: {result}

Réponse:""")
    ])

    # Pipeline complet
    chain = (
        RunnablePassthrough.assign(query=RunnableLambda(generate_sql))
        .assign(result=lambda x: execute_sql(x["query"]))
        | answer_prompt
        | llm
        | StrOutputParser()
    )

    return chain.with_config({"run_name": "TextToSQL_Chain"})


def get_sql_chain_raw():
    """
    Version simplifiée qui retourne juste le résultat SQL brut
    Utile pour VECTOR_SQL où on combine avec du contexte vectoriel

    Returns:
        Chaîne qui retourne le résultat SQL sans formatage
    """
    llm = ChatAnthropic(
        model_name="claude-haiku-4-5-20251001",
        temperature=0,
        api_key=os.getenv("ANTHROPIC_API_KEY")
    )

    db = SQLDatabase.from_uri(
        DB_URL,
        include_tables=[SQL_TABLE],
        sample_rows_in_table_info=3
    )

    sql_prompt = ChatPromptTemplate.from_messages([
        ("system", """Génère UNIQUEMENT une requête SQL PostgreSQL, rien d'autre.
Table: datas {
    id = Column(Integer, primary_key=True, index=True)
    corpus = Column(Text, nullable=False)  # Contenu textuel
    category = Column(String(100), index=True)  # "experience", "competence", "formation", "projet"
    extradatas = Column(JSON, default={})  # Métadonnées structurées
    created_at = Column(DateTime, server_default=func.now()) }

    Exemples de extradatas:
    Pour experience: {"entreprise": "...", "date_debut": "...", "date_fin": "...", "technologies": [...]}
    Pour competence: {"niveau": 4, "type": "backend"}
    Pour projet: {"technologies": [...], "url_github": "...", "annee": 2024}"""),
        ("human", "{question}")
    ])

    execute_query = QuerySQLDatabaseTool(db=db)

    def generate_and_execute(inputs):
        # Générer le SQL
        response = llm.invoke(sql_prompt.format(question=inputs["question"]))
        raw_sql = response.content
        clean_sql = extract_sql_query(raw_sql)

        # Exécuter
        try:
            if clean_sql.strip().upper().startswith("SELECT"):
                result = execute_query.invoke(clean_sql)
                return result if result else "Aucun résultat"
            else:
                return "ERREUR_SQL: Requête invalide"
        except Exception as e:
            return f"ERREUR_SQL: {str(e)}"

    chain = RunnableLambda(generate_and_execute)
    return chain.with_config({"run_name": "TextToSQL_Raw"})


def check_sql_success(result: str) -> bool:
    """
    Vérifie si le résultat SQL est valide (pas une erreur)

    Args:
        result: Résultat de la chaîne SQL

    Returns:
        True si succès, False si erreur
    """
    if not result:
        return False
    result_upper = result.upper()
    return not (
        "ERREUR" in result_upper or
        "ERROR" in result_upper or
        "ERREUR_SQL" in result
    )
