"""
RAG Pipeline avec LangGraph — Orchestration intelligente multi-tables

Correctifs appliqués dans cette version :
  A. LangSmith : RunnableConfig passé à graph.ainvoke → traces visibles
  B. asyncio.get_running_loop() (Python 3.10+, remplace get_event_loop)
  C. SQLDatabase mis en cache par table (singleton) → -1 connexion RDS/appel
  D. ChatAnthropic (Haiku) mis en cache (singleton) → -instanciation/appel
  E. ERREUR_CREDITS : détection 529/402/overloaded dans _execute_sql_on_table
  J. sample_rows_in_table_info=0 → les données réelles ne transitent plus
     dans les prompts Anthropic
"""

import os
import asyncio
import logging
from typing import TypedDict, List, Optional

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langchain_community.utilities import SQLDatabase
from langchain_community.tools import QuerySQLDatabaseTool
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, END

from app.Rag.router import get_intent_router
from app.Rag.retrieval import retrieve_and_rerank, format_context
from app.Rag.generation import rephrase_question_async
from app.Rag.sql_chain import (
    extract_sql_query, check_sql_success,
    get_sql_chain_raw, DB_URL, SQL_TABLE,
)
from app.Rag.vector_store import get_vector_store_service
from langchain_core.documents import Document

load_dotenv()
logger = logging.getLogger("rag_pipeline")


# =============================================================================
# ÉTAT DU GRAPHE
# =============================================================================

class RAGState(TypedDict):
    # --- Entrée ---
    question: str
    session_id: str
    history: List[dict]

    # --- Traitement ---
    rephrased_question: str
    intent: str

    # --- SQL ---
    sql_result: str
    sql_confidence: float       # 1.0=bon 0.7=enrichir 0.5=réessai 0.0=abandon
    explored_tables: List[str]
    sql_iterations: int
    next_table: str

    # --- Vector ---
    vector_docs: List[Document]

    # --- Sortie ---
    context: str
    sources_count: int
    answer: str


# =============================================================================
# SINGLETONS  (Fix C + D)
# =============================================================================

_llm_haiku: Optional[ChatAnthropic] = None
_db_cache: dict[str, SQLDatabase] = {}


def _get_llm_haiku() -> ChatAnthropic:
    """
    Fix D — instance LLM Haiku partagée.
    ChatAnthropic est thread-safe en lecture ; on l'instancie une seule fois.
    """
    global _llm_haiku
    if _llm_haiku is None:
        _llm_haiku = ChatAnthropic(
            model_name="claude-haiku-4-5-20251001",
            temperature=0,
            api_key=os.getenv("ANTHROPIC_API_KEY"),
        )
    return _llm_haiku


def _get_db(table_name: str) -> SQLDatabase:
    """
    Fix C — connexion SQLDatabase mise en cache par table.
    Sans ça, chaque appel SQL ouvrait une nouvelle connexion vers RDS.
    Fix J — sample_rows_in_table_info=0 : aucune ligne d'exemple
             n'est envoyée dans les prompts Anthropic.
    """
    global _db_cache
    if table_name not in _db_cache:
        _db_cache[table_name] = SQLDatabase.from_uri(
            DB_URL,
            include_tables=[table_name],
            sample_rows_in_table_info=0,   # Fix J
        )
    return _db_cache[table_name]


# =============================================================================
# SCHÉMAS PAR TABLE (injectés dans les prompts SQL)
# =============================================================================

_TABLE_SCHEMA = {
    "datas": (
        "id (INT PK), corpus (TEXT), "
        "category (VARCHAR: 'experience'|'competence'|'formation'|'projet'), "
        "extradatas (JSON: {entreprise, date_debut, date_fin, technologies, niveau...}), "
        "created_at (TIMESTAMP)"
    ),
    "portfolio_app_projet": (
        "id (INT PK), titre (VARCHAR), slug (VARCHAR UNIQUE), "
        "description_courte (VARCHAR), description (TEXT), contexte (TEXT), "
        "fonctionnalites (JSONB), resultats (JSONB), "
        "technologies (JSONB: [\"React\",\"TypeScript\"...]), "
        "url_github (VARCHAR), url_demo (VARCHAR), date_realisation (DATE), "
        "est_mis_en_avant (BOOLEAN), est_actif (BOOLEAN), ordre (INT)"
    ),
}


def _get_next_table(explored: List[str]) -> str:
    for table in SQL_TABLE:
        if table not in explored:
            return table
    return ""


# =============================================================================
# HELPER SQL  (Fix B + E)
# =============================================================================

def _execute_sql_on_table(question: str, table_name: str, context_hint: str = "") -> str:
    """
    Génère et exécute une requête SQL ciblée sur une seule table.
    Synchrone — appelé via run_in_executor depuis les nœuds async.

    Fix E — détecte les erreurs de crédits Anthropic (529/402/overloaded)
             et retourne "ERREUR_CREDITS" pour un message UX propre.
    """
    try:
        llm = _get_llm_haiku()                        # Fix D
        db  = _get_db(table_name)                     # Fix C
        executor = QuerySQLDatabaseTool(db=db)

        schema = _TABLE_SCHEMA.get(table_name, "schema inconnu")

        hint_block = ""
        if context_hint and check_sql_success(context_hint):
            hint_block = (
                "\n\nResultat deja obtenu dans une autre table "
                f"(utilise-le comme contexte) :\n{context_hint}"
            )

        prompt = f"""Tu es un expert SQL PostgreSQL. Genere UNIQUEMENT une requete SELECT.

Table cible : {table_name}
Schema : {schema}
{hint_block}

Regles :
- UNIQUEMENT SELECT — aucun DML
- LIMIT 10
- Recherche textuelle : ILIKE '%terme%'
- Champ JSONB tableau : technologies::text ILIKE '%React%'
- Champ JSON objet : extradatas->>'entreprise'
- Si table datas, utilise ce guide de categorie :
    * technologie/langage/outil/framework → category = 'competence'
    * emploi/stage/entreprise/duree       → category = 'experience'
    * diplome/etudes/cours                → category = 'formation'
    * projet realise                      → category = 'projet'
    * doute : PAS de filtre category, cherche dans corpus avec ILIKE

Question : {question}

SQL:"""

        response = llm.invoke(prompt)
        clean_sql = extract_sql_query(response.content)
        logger.debug(f"[_execute_sql_on_table] table={table_name} sql={clean_sql[:100]}")

        if not clean_sql.strip().upper().startswith("SELECT"):
            return "ERREUR_SQL: Requete invalide generee"

        result = executor.invoke(clean_sql)
        return result if result else "Aucun resultat"

    except Exception as exc:
        error_str = str(exc).lower()
        # Fix E — crédits épuisés ou service surchargé
        if any(kw in error_str for kw in ["529", "402", "overloaded", "credit", "quota"]):
            logger.warning(f"[_execute_sql_on_table] Credits Anthropic epuises: {exc}")
            return "ERREUR_CREDITS"
        logger.error(f"[_execute_sql_on_table] table={table_name} erreur={exc}")
        return f"ERREUR_SQL: {exc}"


# =============================================================================
# NŒUDS DU GRAPHE
# =============================================================================

async def rephrase_node(state: RAGState) -> dict:
    # Si l'appelant a déjà reformulé la question (cf. app/main.py, qui fait ce
    # check en amont pour intercepter les demandes de clarification), on ne
    # la recalcule pas — évite un appel LLM redondant.
    if state.get("rephrased_question"):
        return {}
    rephrased = await rephrase_question_async(state["question"], state.get("history", []))
    logger.info(f"[rephrase_node] '{rephrased[:80]}'")
    return {"rephrased_question": rephrased}


async def route_node(state: RAGState) -> dict:
    router = get_intent_router()
    intent = await router.ainvoke({"question": state["rephrased_question"]})
    intent = intent.strip().upper()
    logger.info(f"[route_node] intent={intent}")
    return {"intent": intent}


async def sql_execute_node(state: RAGState) -> dict:
    question = state["rephrased_question"]
    explored = state.get("explored_tables", [])
    target   = _get_next_table(explored) or "datas"

    loop   = asyncio.get_running_loop()              # Fix B
    result = await loop.run_in_executor(
        None, _execute_sql_on_table, question, target, ""
    )

    logger.info(f"[sql_execute_node] table={target} result_len={len(result)}")
    return {
        "sql_result":      result,
        "explored_tables": explored + [target],
        "sql_iterations":  state.get("sql_iterations", 0) + 1,
    }


async def sql_quality_node(state: RAGState) -> dict:
    """
    Evalue la qualite du resultat SQL et fixe sql_confidence.

    conf=1.0 → synthesize (complet)
    conf=0.7 → table_explore (enrichissement)
    conf=0.5 → table_explore (reessai)
    conf=0.0 → vector (fallback)
    """
    result     = state.get("sql_result", "")
    iterations = state.get("sql_iterations", 0)
    explored   = state.get("explored_tables", [])
    next_t     = _get_next_table(explored)

    # Propagation immédiate si crédits épuisés (Fix E)
    if result == "ERREUR_CREDITS":
        logger.warning("[sql_quality_node] ERREUR_CREDITS propagee → synthesize")
        return {"sql_confidence": 1.0, "next_table": ""}

    good_result = check_sql_success(result) and len(result.strip()) > 30

    if iterations >= 2:
        conf = 1.0 if good_result else 0.0
        logger.info(f"[sql_quality_node] max iterations → conf={conf}")
        return {"sql_confidence": conf, "next_table": ""}

    if good_result:
        if next_t:
            logger.info(f"[sql_quality_node] bon resultat, {next_t} dispo → conf=0.7")
            return {"sql_confidence": 0.7, "next_table": next_t}
        logger.info("[sql_quality_node] bon resultat, toutes tables → conf=1.0")
        return {"sql_confidence": 1.0, "next_table": ""}
    else:
        if next_t:
            logger.info(f"[sql_quality_node] vide, table suivante={next_t} → conf=0.5")
            return {"sql_confidence": 0.5, "next_table": next_t}
        logger.info("[sql_quality_node] vide, plus de tables → conf=0.0 (fallback vector)")
        return {"sql_confidence": 0.0, "next_table": ""}


async def table_explore_node(state: RAGState) -> dict:
    question   = state["rephrased_question"]
    next_table = state.get("next_table", "")
    existing   = state.get("sql_result", "")
    explored   = state.get("explored_tables", [])

    if not next_table:
        logger.warning("[table_explore_node] next_table vide — rien a explorer")
        return {}

    loop       = asyncio.get_running_loop()          # Fix B
    new_result = await loop.run_in_executor(
        None, _execute_sql_on_table, question, next_table, existing
    )

    logger.info(f"[table_explore_node] table={next_table} result_len={len(new_result)}")

    # Propagation ERREUR_CREDITS (Fix E)
    if new_result == "ERREUR_CREDITS":
        return {
            "sql_result":      "ERREUR_CREDITS",
            "explored_tables": explored + [next_table],
            "sql_iterations":  state.get("sql_iterations", 0) + 1,
        }

    if check_sql_success(new_result):
        first_table = explored[0] if explored else "table inconnue"
        combined = (
            f"[{first_table}]\n{existing}\n\n[{next_table}]\n{new_result}"
            if check_sql_success(existing)
            else new_result
        )
    else:
        combined = existing

    return {
        "sql_result":      combined,
        "explored_tables": explored + [next_table],
        "sql_iterations":  state.get("sql_iterations", 0) + 1,
    }


async def vector_node(state: RAGState) -> dict:
    vs_service = get_vector_store_service()
    docs = await retrieve_and_rerank(
        query=state["rephrased_question"],
        vector_store_service=vs_service,
        initial_k=8,
        final_k=3,
    )
    logger.info(f"[vector_node] docs={len(docs)}")
    return {"vector_docs": docs}


async def hybrid_node(state: RAGState) -> dict:
    question = state["rephrased_question"]
    sql_raw  = get_sql_chain_raw()

    async def _run_sql():
        return await sql_raw.ainvoke({"question": question})

    async def _run_vector():
        vs = get_vector_store_service()
        return await retrieve_and_rerank(question, vs, initial_k=8, final_k=2)

    sql_res, docs = await asyncio.gather(_run_sql(), _run_vector())

    if isinstance(sql_res, list):
        sql_str = str(sql_res)
    elif isinstance(sql_res, dict):
        sql_str = sql_res.get("result", sql_res.get("output", str(sql_res)))
    else:
        sql_str = str(sql_res)

    logger.info(f"[hybrid_node] sql_len={len(sql_str)} docs={len(docs)}")
    return {"sql_result": sql_str, "vector_docs": docs}


async def synthesize_node(state: RAGState) -> dict:
    parts      = []
    sql_result = state.get("sql_result", "")

    # ERREUR_CREDITS traverse jusqu'ici pour être capturé dans main.py (Fix E)
    if sql_result == "ERREUR_CREDITS":
        logger.warning("[synthesize_node] ERREUR_CREDITS transmis au contexte")
        return {"context": "ERREUR_CREDITS", "sources_count": 0}

    if check_sql_success(sql_result):
        parts.append(f"Donnees structurees (base de donnees) :\n{sql_result}")

    vector_docs = state.get("vector_docs", [])
    if vector_docs:
        parts.append(f"Contexte documentaire :\n{format_context(vector_docs)}")

    context = "\n\n---\n\n".join(parts) if parts else ""
    sources = (1 if check_sql_success(sql_result) else 0) + len(vector_docs)

    logger.info(f"[synthesize_node] context_len={len(context)} sources={sources}")
    return {"context": context, "sources_count": sources}


# =============================================================================
# ROUTAGE CONDITIONNEL
# =============================================================================

def _route_by_intent(state: RAGState) -> str:
    intent = state.get("intent", "VECTOR")
    return {
        "SQL":       "sql_execute",
        "VECTOR_SQL":"hybrid",
        "VECTOR":    "vector",
        "OFF_TOPIC": "synthesize",
    }.get(intent, "vector")


def _route_after_quality(state: RAGState) -> str:
    conf   = state.get("sql_confidence", 0.0)
    next_t = state.get("next_table", "")

    if conf >= 1.0:
        return "synthesize"
    elif next_t:
        return "table_explore"
    else:
        return "vector"


# =============================================================================
# ASSEMBLAGE DU GRAPHE
# =============================================================================

def build_rag_graph():
    graph = StateGraph(RAGState)

    graph.add_node("rephrase",      rephrase_node)
    graph.add_node("route",         route_node)
    graph.add_node("sql_execute",   sql_execute_node)
    graph.add_node("sql_quality",   sql_quality_node)
    graph.add_node("table_explore", table_explore_node)
    graph.add_node("vector",        vector_node)
    graph.add_node("hybrid",        hybrid_node)
    graph.add_node("synthesize",    synthesize_node)

    graph.set_entry_point("rephrase")

    graph.add_edge("rephrase",      "route")
    graph.add_edge("sql_execute",   "sql_quality")
    graph.add_edge("table_explore", "sql_quality")
    graph.add_edge("vector",        "synthesize")
    graph.add_edge("hybrid",        "synthesize")
    graph.add_edge("synthesize",    END)

    graph.add_conditional_edges(
        "route", _route_by_intent,
        {"sql_execute":"sql_execute","hybrid":"hybrid","vector":"vector","synthesize":"synthesize"},
    )
    graph.add_conditional_edges(
        "sql_quality", _route_after_quality,
        {"synthesize":"synthesize","table_explore":"table_explore","vector":"vector"},
    )

    return graph.compile()


_compiled_graph = None


def get_rag_graph():
    global _compiled_graph
    if _compiled_graph is None:
        logger.info("Compilation du graphe LangGraph...")
        _compiled_graph = build_rag_graph()
        logger.info("Graphe LangGraph compile")
    return _compiled_graph


# =============================================================================
# POINT D'ENTRÉE PUBLIC
# =============================================================================

async def run_rag_graph(
    question:           str,
    session_id:         str  = "anonymous",
    history:            list = None,
    rephrased_question: str  = "",
) -> dict:
    """
    Lance le pipeline RAG complet.

    Fix A — RunnableConfig transmis à graph.ainvoke :
      - run_name  → identifie le run dans LangSmith
      - tags      → filtrables dans l'UI LangSmith
      - metadata  → question + session visibles dans chaque trace

    Args:
        rephrased_question: si l'appelant a déjà reformulé la question (ex:
            app/main.py, pour intercepter une demande de clarification avant
            de lancer le pipeline), on la réutilise au lieu de la recalculer.
    """
    graph = get_rag_graph()

    initial_state: RAGState = {
        "question":           question,
        "session_id":         session_id,
        "history":            history or [],
        "rephrased_question": rephrased_question,
        "intent":             "",
        "sql_result":         "",
        "sql_confidence":     0.0,
        "explored_tables":    [],
        "sql_iterations":     0,
        "next_table":         "",
        "vector_docs":        [],
        "context":            "",
        "sources_count":      0,
        "answer":             "",
    }

    # Fix A — LangSmith reçoit maintenant les traces
    config = RunnableConfig(
        run_name="RAG_Pipeline",
        tags=["production", session_id],
        metadata={
            "question":   question[:120],
            "session_id": session_id,
        },
    )

    return await graph.ainvoke(initial_state, config=config)
