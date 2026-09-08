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

# URL de connexion — MÊME source de vérité que app.database (DB_HOST/DB_USER/DB_NAME…),
# avec DATABASE_URL en surcharge optionnelle. Sans ça, en conteneur on retombait sur
# localhost (→ "Connection refused") alors que la DB tourne sur un autre hôte.
from app.database import URL_DATABASE
DB_URL = os.getenv("DATABASE_URL") or URL_DATABASE

# Tables à utiliser pour les requêtes SQL
# NOTE: langchain_pg_embedding est la table interne du vector store — on l'exclut
# pour éviter que le LLM tente du SQL sur des embeddings binaires
SQL_TABLE = ["datas", "portfolio_app_projet"]


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
        model_name="claude-sonnet-5",
        # `temperature` est refusé par ce modèle (400 invalid_request_error) — ne pas le passer.
        api_key=os.getenv("ANTHROPIC_API_KEY")
    )

    db = SQLDatabase.from_uri(
        DB_URL,
        include_tables=SQL_TABLE,
        sample_rows_in_table_info=3
    )

    # Prompt avec classification de table intégrée.
    # Le LLM classe d'abord la question dans une catégorie métier, puis génère
    # une requête SQL ciblée sur la bonne table — sans scanner tout le schéma.
    sql_prompt = ChatPromptTemplate.from_messages([
        ("system", """Tu es un expert SQL PostgreSQL pour le chatbot CV de Yann Jordan Pokam.

SCHÉMA COMPLET:
{table_info}

CARTE DE ROUTAGE (utilise-la AVANT de générer le SQL):

  EXPERIENCES → table datas, category = 'experience'
    emplois, stages, entreprises, durée de travail, années d'expérience
    Ex: "Tu as travaillé où?" / "Combien d'années chez Globatech?"

  COMPETENCES → table datas, category = 'competence'
    technologies, langages, frameworks, outils, niveaux
    IMPORTANT : "expérience en React/Python/C#/..." = compétence, PAS expérience !
    Ex: "Quel est ton niveau en React?" / "Tu connais Python?" / "Expérience en TypeScript?"

  FORMATION → table datas, category = 'formation'
    diplômes, études, cégep, cours
    Ex: "Quel diplôme tu as?" / "Tu as étudié où?"

  PROJETS_LISTE → table portfolio_app_projet
    lister, compter, filtrer des projets
    Ex: "Combien de projets?" / "Projets en React?"

  PROJETS_DETAIL → table portfolio_app_projet
    détails d'un projet précis, date, technologies utilisées
    Ex: "Décris SuperCChic" / "Ton projet le plus récent?"

  MIXTE → deux SELECT indépendants (datas ET portfolio_app_projet)
    questions mélant compétences/expériences ET projets
    Ex: "Projets en C# et ton niveau C#?" → deux SELECT séparés par point-virgule

  DOUTE sur la catégorie datas → NE PAS filtrer par category,
    cherche directement dans corpus avec ILIKE '%terme%'

RÈGLES SQL:
1. Génère UNIQUEMENT la requête SQL, sans commentaire ni explication
2. Utilise ILIKE '%mot%' pour les recherches textuelles
3. Limite à 10 résultats (LIMIT 10)
4. Pour filtrer un JSONB : technologies::text ILIKE '%React%'
5. Pour extraire un champ JSON de datas.extradatas : extradatas->>'entreprise'
6. Pour la table datas : les colonnes sont id, corpus, category, extradatas, created_at
7. Pour portfolio_app_projet : ne suppose PAS corpus ni extradatas — ce n'est pas la même table
"""),
        ("human", "Question: {question}\n\nSQL:")
    ])

    def generate_sql(inputs):
        table_info = db.get_table_info()
        # ✅ format_messages() retourne une liste de BaseMessage, correct pour llm.invoke()
        messages = sql_prompt.format_messages(
            table_info=table_info,
            question=inputs["question"]
        )
        response = llm.invoke(messages)
        raw_sql = response.content
        clean_sql = extract_sql_query(raw_sql)
        logger.debug(f"SQL brut: {raw_sql[:100]}...")
        logger.debug(f"SQL extrait: {clean_sql}")
        return clean_sql

    execute_query = QuerySQLDatabaseTool(db=db)

    def execute_sql(sql: str) -> str:
        try:
            if not sql or not sql.strip().upper().startswith("SELECT"):
                return "ERREUR: Requête SQL invalide"
            result = execute_query.invoke(sql)
            return result if result else "Aucun résultat trouvé"
        except Exception as e:
            logger.error(f"Erreur SQL: {e}")
            return f"ERREUR_SQL: {str(e)}"

    # NOTE: Même chose ici, aucune accolade littérale dans le texte statique du prompt.
    answer_prompt = ChatPromptTemplate.from_messages([
        ("system", """Tu es un assistant qui répond aux questions sur le CV de Yann.

Utilise le résultat de la requête SQL pour formuler une réponse naturelle et professionnelle.

RÈGLES:
- Si le résultat commence par ERREUR, indique qu'il y a eu un problème technique
- Si le résultat est vide ou Aucun résultat, dis que tu n'as pas trouvé l'information
- Ne mentionne JAMAIS la requête SQL ou les détails techniques
- Formule une réponse conversationnelle et utile"""),
        ("human", """Question: {question}

Résultat de la recherche: {result}

Réponse:""")
    ])

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
    Version simplifiée qui retourne juste le résultat SQL brut.
    Utile pour VECTOR_SQL où on combine avec du contexte vectoriel.

    Returns:
        Chaîne qui retourne le résultat SQL sans formatage LLM final
    """
    llm = ChatAnthropic(
        model_name="claude-sonnet-5",
        # `temperature` est refusé par ce modèle (400 invalid_request_error) — ne pas le passer.
        api_key=os.getenv("ANTHROPIC_API_KEY")
    )

    db = SQLDatabase.from_uri(
        DB_URL,
        include_tables=SQL_TABLE,
        sample_rows_in_table_info=3
    )

    # Même carte de routage que get_sql_chain() — prompt unifié.
    # Les accolades littérales JSON dans les exemples sont doublées ({{ }}).
    sql_prompt = ChatPromptTemplate.from_messages([
        ("system", """Tu es un expert SQL PostgreSQL pour le chatbot CV de Yann Jordan Pokam.
Génère UNIQUEMENT la requête SQL, sans explication.

SCHÉMA:

table datas:
    id          INTEGER PRIMARY KEY
    corpus      TEXT NOT NULL
    category    VARCHAR(100)  -- valeurs: 'experience', 'competence', 'formation', 'projet'
    extradatas  JSON DEFAULT {{}}  -- ex: {{"entreprise":"...","date_debut":"...","technologies":[...]}}
    created_at  TIMESTAMP

table portfolio_app_projet:
    id                  INTEGER PRIMARY KEY
    titre               VARCHAR(200)
    slug                VARCHAR(200) UNIQUE
    description_courte  VARCHAR(300)
    description         TEXT
    contexte            TEXT
    fonctionnalites     JSONB
    resultats           JSONB
    technologies        JSONB   -- ex: ["React","TypeScript"]
    url_github          VARCHAR(200)
    url_demo            VARCHAR(200)
    date_realisation    DATE
    est_mis_en_avant    BOOLEAN
    est_actif           BOOLEAN
    ordre               INTEGER
    created_at          TIMESTAMP WITH TIME ZONE
    updated_at          TIMESTAMP WITH TIME ZONE

CARTE DE ROUTAGE (utilise-la AVANT de générer le SQL):

  EXPERIENCES → datas WHERE category = 'experience'
    emplois, stages, entreprises, durée de travail

  COMPETENCES → datas WHERE category = 'competence'
    technologies, langages, frameworks, outils, niveaux
    ATTENTION : "expérience en React/Python/..." = compétence, PAS expérience !

  FORMATION → datas WHERE category = 'formation'
    diplômes, études, cégep, cours

  PROJETS_LISTE / PROJETS_DETAIL → portfolio_app_projet
    lister, compter, filtrer, détailler des projets

  MIXTE → deux SELECT séparés par un point-virgule
    questions mélant compétences/expériences ET projets

  DOUTE sur la catégorie → cherche dans corpus avec ILIKE, sans filtre category

RÈGLES SQL:
1. UNIQUEMENT SELECT, pas de DML
2. ILIKE '%mot%' pour les recherches textuelles
3. LIMIT 10
4. JSON tableau : technologies::text ILIKE '%React%'
5. JSON champ : extradatas->>'entreprise'
6. portfolio_app_projet n'a PAS de colonne corpus ni extradatas
"""),
        ("human", "{question}")
    ])

    execute_query = QuerySQLDatabaseTool(db=db)

    def generate_and_execute(inputs: dict) -> str:
        # ✅ format_messages() retourne une liste de BaseMessage, correct pour llm.invoke()
        messages = sql_prompt.format_messages(question=inputs["question"])
        response = llm.invoke(messages)
        raw_sql = response.content
        clean_sql = extract_sql_query(raw_sql)
        logger.debug(f"[RAW] SQL brut: {raw_sql[:100]}...")
        logger.debug(f"[RAW] SQL extrait: {clean_sql}")

        try:
            if clean_sql.strip().upper().startswith("SELECT"):
                result = execute_query.invoke(clean_sql)
                return result if result else "Aucun résultat"
            else:
                logger.warning(f"[RAW] Requête invalide générée: {clean_sql[:100]}")
                return "ERREUR_SQL: Requête invalide"
        except Exception as e:
            logger.error(f"[RAW] Erreur exécution SQL: {e}")
            return f"ERREUR_SQL: {str(e)}"

    chain = RunnableLambda(generate_and_execute)
    return chain.with_config({"run_name": "TextToSQL_Raw"})


def check_sql_success(result: str) -> bool:
    """
    Vérifie si le résultat SQL est valide (non vide, non erroné).

    Cas détectés comme échec :
    - None ou chaîne vide
    - Erreurs explicites (ERREUR, ERROR, ERREUR_SQL)
    - Résultats vides PostgreSQL : [], [()], (), "Aucun résultat"
    - Réponses trop courtes pour être utiles (< 5 caractères)

    Args:
        result: Résultat de la chaîne SQL

    Returns:
        True si le résultat contient de l'information utile
    """
    if not result or not result.strip():
        return False

    stripped = result.strip()

    # Résultat trop court pour être utile
    if len(stripped) < 5:
        return False

    upper = stripped.upper()

    # Erreurs explicites
    if any(kw in upper for kw in ["ERREUR_SQL", "ERREUR:", "ERROR:"]):
        return False

    # Résultats vides courants retournés par PostgreSQL / LangChain
    empty_patterns = {
        "[]", "[()]", "()", "NONE",
        "AUCUN RÉSULTAT", "AUCUN RESULTAT",
        "NO RESULTS", "AUCUNE DONNÉE"
    }
    if upper in empty_patterns:
        return False

    return True