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
from sqlalchemy.pool import NullPool
from dotenv import load_dotenv
import os
import re
import logging

# NullPool + pool_pre_ping pour toutes les connexions SQLDatabase de ce module :
# sur une base serverless (Neon), une connexion pool par défaut finit par être
# coupée après suspension du compute ("SSL connection has been closed
# unexpectedly" au prochain appel).
_NEON_SAFE_ENGINE_ARGS = {"poolclass": NullPool, "pool_pre_ping": True}

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
# `datas` est un cache dérivé. Le SQL ne le lit plus : les faits sont dans les tables canoniques.
SQL_TABLE = [
    "portfolio_app_projet",
    "portfolio_app_experience",
    "portfolio_app_formation",
    "portfolio_app_competence",
    "portfolio_app_infopersonnelle",
]


# Tables citées après FROM / JOIN (les fonctions du type EXTRACT(YEAR FROM …)
# sont retirées avant l'analyse pour ne pas être prises pour des tables).
_TABLE_REF = re.compile(r"\b(?:from|join)\s+(\"?[a-zA-Z_][\w.]*\"?)", re.IGNORECASE)
_FROM_FUNCS = re.compile(r"\b(?:extract|substring|trim|overlay)\s*\([^)]*\)", re.IGNORECASE)


def canonical_sql_or_error(sql: str) -> str | None:
    """
    Garde des requêtes générées par un LLM. Refuse :
      - ce qui n'est pas un SELECT unique ;
      - toute lecture du cache `datas` ;
      - toute table hors des tables canoniques (SQL_TABLE) — chat_sessions,
        testimonials, faq… ne sont jamais lisibles par ce chemin ;
      - la colonne telephone, y compris via SELECT * sur le profil.
    """
    if not sql or not sql.strip().upper().startswith("SELECT"):
        return "ERREUR: Requête SQL invalide"
    if re.search(r"\bdatas\b", sql, re.IGNORECASE):
        return "ERREUR_SQL: la table datas n'est pas une source de faits"
    if ";" in sql.strip().rstrip(";"):
        return "ERREUR_SQL: une seule requête à la fois"
    if re.search(r"\btelephone\b", sql, re.IGNORECASE):
        return "ERREUR_SQL: la colonne telephone n'est pas lisible"
    tables = {t.strip('"').split(".")[-1].lower() for t in _TABLE_REF.findall(_FROM_FUNCS.sub(" ", sql))}
    refused = sorted(tables - set(SQL_TABLE))
    if refused:
        return f"ERREUR_SQL: tables non autorisées : {', '.join(refused)}"
    if "portfolio_app_infopersonnelle" in tables and re.search(r"(select|,)\s*(\w+\.)?\*", sql, re.IGNORECASE):
        return "ERREUR_SQL: liste les colonnes du profil (pas de SELECT *)"
    return None


def extract_sql_query(text: str) -> str:
    """Extrait uniquement le SELECT de la sortie du modèle."""
    if not text:
        return ""

    text = text.strip()

    match = re.search(r'SQLQuery:\s*(SELECT.+?)(?:;|$)', text, re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip() + ";"

    match = re.search(r'```sql\s*(SELECT.+?)\s*```', text, re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()

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
        sample_rows_in_table_info=3,
        engine_args=_NEON_SAFE_ENGINE_ARGS,
    )

    # Prompt avec classification de table intégrée.
    # Le LLM classe d'abord la question dans une catégorie métier, puis génère
    # une requête SQL ciblée sur la bonne table — sans scanner tout le schéma.
    sql_prompt = ChatPromptTemplate.from_messages([
        ("system", """Tu es un expert SQL PostgreSQL pour le chatbot CV de Jordan Pokam Teguia.

SCHÉMA COMPLET:
{table_info}

CARTE DE ROUTAGE (utilise-la AVANT de générer le SQL):

  EXPERIENCES → portfolio_app_experience WHERE est_actif = TRUE
    emplois, stages, entreprises

  COMPETENCES → portfolio_app_competence WHERE est_actif = TRUE
    technologies, langages, frameworks. "expérience en React" = compétence.

  FORMATION → portfolio_app_formation WHERE est_actif = TRUE
    diplômes, études, cégep

  PROJETS_LISTE → portfolio_app_projet WHERE est_actif = TRUE
  PROJETS_DETAIL → portfolio_app_projet WHERE est_actif = TRUE
  IDENTITE / CONTACT → portfolio_app_infopersonnelle
    jamais la colonne telephone

  N'utilise JAMAIS la table datas.

RÈGLES SQL:
1. Génère UNIQUEMENT la requête SQL, sans commentaire ni explication
2. Utilise ILIKE '%mot%' pour les recherches textuelles
3. Limite à 10 résultats (LIMIT 10)
4. Pour filtrer un texte JSON : technologies::text ILIKE '%React%'
5. Pas de colonne corpus ni extradatas
6. Si la table a est_actif : TOUJOURS WHERE est_actif = TRUE
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
            refused = canonical_sql_or_error(sql)
            if refused:
                return refused
            result = execute_query.invoke(sql)
            return result if result else "Aucun résultat trouvé"
        except Exception as e:
            logger.error(f"Erreur SQL: {e}")
            return f"ERREUR_SQL: {str(e)}"

    # NOTE: Même chose ici, aucune accolade littérale dans le texte statique du prompt.
    answer_prompt = ChatPromptTemplate.from_messages([
        ("system", """Tu es un assistant qui répond aux questions sur le CV de Jordan.

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
        sample_rows_in_table_info=3,
        engine_args=_NEON_SAFE_ENGINE_ARGS,
    )

    # Même carte de routage que get_sql_chain() — prompt unifié.
    # Les accolades littérales JSON dans les exemples sont doublées ({{ }}).
    sql_prompt = ChatPromptTemplate.from_messages([
        ("system", """Tu es un expert SQL PostgreSQL pour le chatbot CV de Jordan Pokam Teguia.
Génère UNIQUEMENT la requête SQL, sans explication.

SCHÉMA:
Les faits sont dans portfolio_app_projet, portfolio_app_experience,
portfolio_app_formation, portfolio_app_competence, portfolio_app_infopersonnelle.
N'utilise JAMAIS la table datas. Ne sélectionne jamais telephone.

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

  EXPERIENCES → portfolio_app_experience WHERE est_actif = TRUE
  COMPETENCES → portfolio_app_competence WHERE est_actif = TRUE
  FORMATION → portfolio_app_formation WHERE est_actif = TRUE
  PROJETS → portfolio_app_projet WHERE est_actif = TRUE
  IDENTITE → portfolio_app_infopersonnelle
  N'utilise JAMAIS la table datas.

RÈGLES SQL:
1. UNIQUEMENT SELECT, pas de DML
2. ILIKE '%mot%' pour les recherches textuelles
3. LIMIT 10
4. technologies::text ILIKE '%React%'
5. Pas de corpus ni extradatas
6. Si est_actif existe : TOUJOURS WHERE est_actif = TRUE
7. Ne jamais sélectionner telephone
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
            refused = canonical_sql_or_error(clean_sql)
            if refused:
                return refused
            result = execute_query.invoke(clean_sql)
            return result if result else "Aucun résultat"
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