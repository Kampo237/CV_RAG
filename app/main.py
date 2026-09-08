"""
FastAPI Application - Chatbot CV avec RAG Avancé

Pipeline RAG:
1. Rate Limiting (optionnel)
2. Récupération historique
3. Reformulation de la question
4. Routage sémantique (SQL / VECTOR / VECTOR_SQL / OFF_TOPIC)
5. Récupération du contexte (SQL ou Vectoriel + Rerank)
6. Génération de la réponse
7. Sauvegarde de l'interaction
"""
from fastapi import FastAPI, HTTPException, Depends, Request, APIRouter, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Annotated
from sqlalchemy.orm import Session
from contextlib import asynccontextmanager
import time
import logging
import traceback
from fastapi.responses import StreamingResponse, JSONResponse
import json
import asyncio
from datetime import datetime
import os, traceback, json, uuid, re

# =============================================================================
# CONFIGURATION DU LOGGING
# =============================================================================

# Créer un logger personnalisé
logger = logging.getLogger("rag_pipeline")
# Fix H — niveau DEBUG uniquement en dev, INFO en production
_ENV = os.getenv("ENVIRONMENT", "development").lower()
logger.setLevel(logging.DEBUG if _ENV != "production" else logging.INFO)

# Format détaillé avec timestamp, niveau, et message
formatter = logging.Formatter(
    '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Handler console (coloré)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
console_handler.setFormatter(formatter)

# Handler fichier (pour historique)
log_path = os.path.join(os.path.dirname(__file__), "rag_pipeline.log")
file_handler = logging.FileHandler(log_path, encoding='utf-8')
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(formatter)

# Ajouter les handlers
logger.addHandler(console_handler)
logger.addHandler(file_handler)

# Désactiver les logs verbeux de certaines librairies
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("anthropic").setLevel(logging.WARNING)


# =============================================================================
# CLASSE UTILITAIRE POUR MESURER LE TEMPS
# =============================================================================

class PipelineTimer:
    """Mesure le temps d'exécution de chaque étape"""

    def __init__(self, request_id: str):
        self.request_id = request_id
        self.start_time = time.time()
        self.steps = {}
        self.current_step = None
        self.step_start = None

    def start_step(self, step_name: str):
        """Démarre le chrono pour une étape"""
        self.current_step = step_name
        self.step_start = time.time()
        logger.info(f"[{self.request_id}] ▶️  DÉBUT: {step_name}")

    def end_step(self, extra_info: str = ""):
        """Termine le chrono pour l'étape courante"""
        if self.current_step and self.step_start:
            duration = (time.time() - self.step_start) * 1000  # en ms
            self.steps[self.current_step] = duration
            info = f" | {extra_info}" if extra_info else ""
            logger.info(f"[{self.request_id}] ✅ FIN: {self.current_step} ({duration:.0f}ms){info}")
            self.current_step = None

    def total_time(self) -> float:
        """Retourne le temps total en ms"""
        return (time.time() - self.start_time) * 1000

    def summary(self) -> dict:
        """Retourne un résumé des temps"""
        return {
            "request_id": self.request_id,
            "total_ms": round(self.total_time(), 0),
            "steps": {k: round(v, 0) for k, v in self.steps.items()}
        }


# =============================================================================
# IMPORTS LOCAUX
# =============================================================================

from app import models
from app.database import engine, get_db

# Imports RAG
from app.Rag import (
    get_intent_router,
    get_sql_chain,
    VectorStoreService,
    get_vector_store_service,
    run_rag_graph,          # pipeline La ngGraph unifié
    run_rag_agent,
    load_document,
    semantic_chunk,
)
from app.Rag.retrieval import format_context, retrieve_and_rerank
from app.Rag.generation import (
    rephrase_question_async,
    generate_response,
    is_clarification_request,
    extract_clarification_question,
)
from app.Rag.sql_chain import get_sql_chain_raw

from dotenv import load_dotenv

load_dotenv()


# =============================================================================
# CONFIGURATION FASTAPI
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle: Initialisation au démarrage"""
    logger.info("🚀 Démarrage de l'application RAG Chatbot")
    # Fix — une base serverless (Neon) qui se réveille peut être lente/indisponible
    # quelques instants au cold start. Un échec ici ne doit plus faire planter
    # tout le process (c'est exactement ce qui a fait tomber l'API avec binatonedb).
    try:
        models.Base.metadata.create_all(bind=engine)
        logger.info("✅ Tables créées/vérifiées")
    except Exception as e:
        logger.error(f"❌ Impossible de créer/vérifier les tables au démarrage: {e}")
        logger.error("   L'API démarre quand même — les routes qui dépendent de la DB échoueront tant qu'elle n'est pas joignable.")

    # Pre-chauffage du graphe LangGraph au boot
    # Sans ca, la 1re requete paie le cout de compilation (~200ms)
    try:
        from app.Rag.graph import get_rag_graph
        get_rag_graph()
        logger.info("✅ Graphe LangGraph pre-chauffe")
    except Exception as e:
        logger.warning(f"⚠️ Pre-chauffe LangGraph echoue: {e}")

    yield
    logger.info("👋 Arret de l'application")


app = FastAPI(
    title="CV Chatbot API",
    description="API RAG pour le portfolio de Yann Willy Jordan Pokam Teguia",
    version="1.0.0",
    lifespan=lifespan
)

# CORS pour le frontend Django
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# MIDDLEWARE DE LOGGING DES REQUÊTES
# =============================================================================

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log toutes les requêtes HTTP"""
    request_id = f"REQ-{int(time.time() * 1000) % 100000}"

    logger.info(f"[{request_id}] 📥 {request.method} {request.url.path}")

    start_time = time.time()
    response = await call_next(request)
    duration = (time.time() - start_time) * 1000

    status_emoji = "✅" if response.status_code < 400 else "❌"
    logger.info(f"[{request_id}] {status_emoji} {response.status_code} ({duration:.0f}ms)")

    return response


# =============================================================================
# MODÈLES PYDANTIC
# =============================================================================

class QuestionRequest(BaseModel):
    """Requête de chat"""
    question: str
    session_id: Optional[str] = None
    category: Optional[str] = None


class ChatResponse(BaseModel):
    """Réponse du chatbot"""
    answer: str
    intent: str
    sources_count: int = 0
    debug: Optional[dict] = None  # Infos de debug optionnelles


class EmbeddingRequest(BaseModel):
    """Requête pour ajouter des connaissances"""
    message_text: str
    category: str
    metadata: dict = {}


class Message(BaseModel):
    role: str
    content: str

class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[Message]
    stream: Optional[bool] = True
    temperature: Optional[float] = 0.8


# =============================================================================
# MODÈLES TESTIMONIAL
# =============================================================================

class TestimonialBase(BaseModel):
    author_name: str
    author_email: str
    author_company: Optional[str] = None
    author_position: Optional[str] = None
    content: str
    rating: int  # Tu peux ajouter une validation ex: Field(..., ge=1, le=5)

class TestimonialCreate(TestimonialBase):
    pass

class TestimonialUpdateStatus(BaseModel):
    """Pour approuver ou mettre en avant via Swagger"""
    is_approved: Optional[bool] = None
    is_featured: Optional[bool] = None

class TestimonialResponse(TestimonialBase):
    id: int
    is_approved: bool
    is_featured: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# =============================================================================
# DÉPENDANCES
# =============================================================================

db_dependency = Annotated[Session, Depends(get_db)]

_router = None
_sql_chain = None


def get_router():
    global _router
    if _router is None:
        logger.debug("Initialisation du router sémantique...")
        _router = get_intent_router()
        logger.debug("Router initialisé ✓")
    return _router


def get_sql():
    global _sql_chain
    if _sql_chain is None:
        logger.debug("Initialisation de la chaîne SQL...")
        _sql_chain = get_sql_chain()
        logger.debug("Chaîne SQL initialisée ✓")
    return _sql_chain


# =============================================================================
# STOCKAGE D'HISTORIQUE (PostgreSQL)
# =============================================================================

MAX_HISTORY_MESSAGES = 20  # Garder les 20 derniers messages (10 échanges)


def get_chat_history(session_id: str, db: Session) -> List[dict]:
    """Récupère l'historique d'une session depuis PostgreSQL."""
    session = db.query(models.ChatSession).filter(
        models.ChatSession.session_id == session_id
    ).first()

    if not session:
        logger.debug(f"Aucune session trouvée pour {session_id}")
        return []

    messages = session.messages or []
    logger.debug(f"Historique récupéré: {len(messages)} messages (session {session_id})")
    return messages


def save_interaction(session_id: str, question: str, answer: str, db: Session):
    """Sauvegarde un échange question/réponse dans PostgreSQL.

    Crée la session si elle n'existe pas, sinon ajoute les messages.
    Limite à MAX_HISTORY_MESSAGES pour éviter que le contexte LLM explose.
    """
    session = db.query(models.ChatSession).filter(
        models.ChatSession.session_id == session_id
    ).first()

    new_messages = [
        {"role": "user", "content": question},
        {"role": "assistant", "content": answer},
    ]

    if session is None:
        # Première interaction de ce visiteur
        session = models.ChatSession(
            session_id=session_id,
            messages=new_messages,
            message_count=2,
        )
        db.add(session)
    else:
        # Append aux messages existants, tronquer si trop long
        current = session.messages or []
        updated = current + new_messages

        if len(updated) > MAX_HISTORY_MESSAGES:
            updated = updated[-MAX_HISTORY_MESSAGES:]

        session.messages = updated
        session.message_count = len(updated)
        # Force SQLAlchemy à détecter le changement sur la colonne JSON
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(session, "messages")

    db.commit()
    logger.debug(f"Interaction sauvegardée pour session {session_id} ({session.message_count} messages)")


# =============================================================================
# RATE LIMITING
# =============================================================================

_request_counts: dict[str, int] = {}
# Fix I — lit la valeur depuis .env (MAX_REQUESTS_PER_SESSION=10 dans .env)
# Fallback a 50 si la variable n'est pas definie
MAX_REQUESTS_PER_SESSION = int(os.getenv("MAX_REQUESTS_PER_SESSION", "50"))
RAG_MODE = os.getenv("RAG_MODE", "automate")  # "automate" ou "agent"

def check_rate_limit(session_id: str) -> bool:
    if not session_id:
        return True

    count = _request_counts.get(session_id, 0)
    if count >= MAX_REQUESTS_PER_SESSION:
        logger.warning(f"⚠️ Rate limit atteint pour session {session_id}")
        return False

    _request_counts[session_id] = count + 1
    logger.debug(f"Rate limit: {count + 1}/{MAX_REQUESTS_PER_SESSION}")
    return True


# =============================================================================
# ALERTES SMS SILENCIEUSES (fire-and-forget)
# =============================================================================

JORDAN_PHONE = os.getenv("JORDAN_PHONE")  # doit être défini en .env — pas de valeur en dur dans le code


def _summarize_error(exc: Exception) -> str:
    """
    Résumé court et lisible d'une exception pour les alertes SMS.

    Les erreurs API (Anthropic, etc.) arrivent souvent sous la forme
    "Error code: 400 - {'type': 'error', 'error': {..., 'message': '...'}}" :
    du JSON brut illisible une fois tronqué sur un écran de SMS. On en extrait
    juste le champ "message" quand c'est possible, sinon on retombe sur le nom
    du type d'exception + le début du message.
    """
    raw = str(exc)
    match = re.search(r"[\"']message[\"']\s*:\s*[\"']([^\"']+)[\"']", raw)
    if match:
        return f"{type(exc).__name__}: {match.group(1)}"
    return f"{type(exc).__name__}: {raw[:200]}"


async def send_alert_sms(message: str, level: str = "INFO"):
    """
    Envoie un SMS d'alerte à Jordan en arrière-plan.
    
    Fire-and-forget : n'interrompt JAMAIS le flux utilisateur.
    Appelle Twilio directement (pas via MCP) pour être indépendant
    du serveur MCP.
    
    Niveaux :
      - INFO  : visiteur intéressant, interaction notable
      - WARN  : comportement suspect, rate limit, tentative d'abus
      - ERROR : erreur technique, crash, DB indisponible

    Le message est tronqué à 1500 car. — Twilio segmente automatiquement les SMS
    concaténés au-delà de 160 car., donc pas besoin de couper à 160 : ça coupait
    des messages d'erreur en plein milieu (ex. un JSON d'erreur Anthropic).
    """
    def _send_sync():
        try:
            from twilio.rest import Client

            sid = os.getenv("TWILIO_ACCOUNT_SID")
            token = os.getenv("TWILIO_AUTH_TOKEN")
            from_number = os.getenv("TWILIO_FROM_NUMBER")

            if not all([sid, token, from_number, JORDAN_PHONE]):
                logger.warning("[ALERT_SMS] Config Twilio incomplète, alerte ignorée")
                return

            # Préfixer avec le niveau et tronquer (large marge, cf. docstring)
            prefix = f"[{level}] "
            truncated = prefix + message[:1500 - len(prefix)]
            
            client = Client(sid, token)
            client.messages.create(
                body=truncated,
                from_=from_number,
                to=JORDAN_PHONE,
            )
            logger.info(f"[ALERT_SMS] {level} envoyé à {JORDAN_PHONE}")
            
        except Exception as e:
            # Ne JAMAIS propager l'erreur — l'alerte est secondaire
            logger.error(f"[ALERT_SMS] Échec envoi: {e}")

    # Exécuter dans un thread séparé pour ne pas bloquer l'event loop
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, _send_sync)


# =============================================================================
# ANTI-ABUS / PROTECTION DES CRÉDITS LLM
# Filtres bon marché exécutés AVANT tout appel payant à Anthropic, pour qu'un
# bot qui fait tourner les session_id ne puisse pas épuiser les crédits.
# État en mémoire (mono-process) : suffisant pour un déploiement single-worker.
# =============================================================================
import collections

MAX_QUESTION_CHARS = int(os.getenv("MAX_QUESTION_CHARS", "600"))   # rejette le bourrage de prompt
IP_WINDOW_SECONDS  = int(os.getenv("IP_WINDOW_SECONDS", "60"))     # fenêtre glissante par IP
IP_MAX_IN_WINDOW   = int(os.getenv("IP_MAX_IN_WINDOW", "12"))      # max requêtes / IP / fenêtre
DAILY_LLM_BUDGET   = int(os.getenv("DAILY_LLM_BUDGET", "500"))     # disjoncteur : appels max / jour
ALERT_COOLDOWN_SEC = int(os.getenv("ALERT_COOLDOWN_SEC", "600"))   # anti-spam SMS (par clé)

_ip_hits: dict[str, "collections.deque[float]"] = collections.defaultdict(collections.deque)
_daily_budget = {"day": None, "count": 0, "tripped": False}
_last_alert: dict[str, float] = {}


def _client_ip(http_request: Request) -> str:
    """IP réelle du visiteur (le proxy Caddy pose X-Forwarded-For)."""
    xff = http_request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    return http_request.client.host if http_request.client else "unknown"


def _should_alert(key: str) -> bool:
    """True au plus une fois par `key` toutes les ALERT_COOLDOWN_SEC (anti-spam SMS)."""
    now = time.time()
    if now - _last_alert.get(key, 0) >= ALERT_COOLDOWN_SEC:
        _last_alert[key] = now
        return True
    return False


def screen_request(ip: str, question: str) -> tuple[bool, str]:
    """Filtre AVANT tout LLM. Renvoie (autorisé, raison_du_blocage)."""
    q = (question or "").strip()
    if not q:
        return False, "question vide"
    if len(q) > MAX_QUESTION_CHARS:
        return False, f"question trop longue ({len(q)} car.)"

    now = time.time()
    dq = _ip_hits[ip]
    while dq and now - dq[0] > IP_WINDOW_SECONDS:
        dq.popleft()
    if len(dq) >= IP_MAX_IN_WINDOW:
        return False, f"burst IP {len(dq)}/{IP_WINDOW_SECONDS}s"
    dq.append(now)
    return True, ""


def consume_daily_budget() -> tuple[bool, bool]:
    """Disjoncteur quotidien d'appels LLM. Renvoie (autorisé, vient_de_déclencher)."""
    today = time.strftime("%Y-%m-%d")
    if _daily_budget["day"] != today:
        _daily_budget.update(day=today, count=0, tripped=False)
    if _daily_budget["count"] >= DAILY_LLM_BUDGET:
        just_tripped = not _daily_budget["tripped"]
        _daily_budget["tripped"] = True
        return False, just_tripped
    _daily_budget["count"] += 1
    return True, False


# =============================================================================
# ROUTE PRINCIPALE - CHAT AVEC LOGS DÉTAILLÉS
# =============================================================================

@app.get("/")
async def root():
    return {"message": "Salut chef 👋", "status": "online"}


@app.post("/chat/")
async def chat(request: QuestionRequest, http_request: Request):
    """
    Pipeline complet RAG avec streaming et métadonnées finales.
    """

    async def event_stream():
        request_id = f"CHAT-{int(time.time() * 1000) % 100000}"
        timer = PipelineTimer(request_id)

        logger.info("=" * 60)
        logger.info(f"[{request_id}] 🎤 NOUVELLE QUESTION: {request.question[:100]}...")
        logger.info("=" * 60)

        # Ouvrir une session DB manuellement (le générateur async
        # ne peut pas utiliser Depends(get_db))
        from app.database import SessionLocal
        db = SessionLocal()

        try:
            session_id = request.session_id or "anonymous"
            logger.debug(f"[{request_id}] Session ID: {session_id}")

            # =====================================================================
            # 1. RATE LIMITING
            # =====================================================================
            timer.start_step("1_RATE_LIMITING")
            if not check_rate_limit(session_id):
                timer.end_step("BLOCKED")
                yield "⚠️ Tu as atteint la limite de messages pour cette session. Actualise la page ou reviens un peu plus tard. Merci pour ton intérêt !"
                return
            timer.end_step("OK")

            # =====================================================================
            # 1b. ANTI-ABUS / PROTECTION CRÉDITS (IP, contenu, budget quotidien)
            #     Tout ceci s'exécute AVANT le moindre appel LLM payant.
            # =====================================================================
            timer.start_step("1B_ANTIABUS")
            ip = _client_ip(http_request)

            allowed, reason = screen_request(ip, request.question)
            if not allowed:
                logger.warning(f"[{request_id}] 🛑 Bloqué ({reason}) ip={ip} session={session_id[:8]}")
                # SMS de diagnostic (throttlé par IP pour ne pas te spammer)
                if _should_alert(f"abuse:{ip}"):
                    await send_alert_sms(
                        f"ABUS bloqué ({reason}) ip={ip} q='{request.question[:35]}'",
                        level="WARN",
                    )
                timer.end_step(f"BLOQUÉ ({reason})")
                yield "⚠️ Trop de requêtes ou requête invalide. Réessaie dans un petit moment."
                return

            budget_ok, just_tripped = consume_daily_budget()
            if not budget_ok:
                # Disjoncteur : on a atteint le plafond d'appels du jour → on coupe.
                if just_tripped:
                    await send_alert_sms(
                        f"BUDGET LLM quotidien atteint ({DAILY_LLM_BUDGET}) — circuit ouvert, appels stoppés",
                        level="ERROR",
                    )
                logger.warning(f"[{request_id}] 🧯 Budget quotidien atteint — requête refusée (ip={ip})")
                timer.end_step("BUDGET_QUOTIDIEN")
                yield "⚠️ L'assistant a atteint sa limite d'utilisation pour aujourd'hui. Reviens demain, ou écris-moi sur LinkedIn :)"
                return
            timer.end_step(f"OK ip={ip}")

            # =====================================================================
            # 2. RÉCUPÉRATION HISTORIQUE (depuis PostgreSQL)
            # =====================================================================
            timer.start_step("2_HISTORIQUE")
            history = get_chat_history(session_id, db)
            timer.end_step(f"{len(history)} messages")

            # =====================================================================
            # 2B. REFORMULATION (faite une seule fois ici, en amont du pipeline)
            #
            # Si le message est trop vague pour être reformulé en question
            # autonome (ex: "euhh", "vasy voir..."), on ne lance PAS le
            # pipeline RAG dessus : ça reviendrait à demander à l'agent de
            # "répondre" à une question de clarification au lieu de la
            # reposer au visiteur. On répond directement avec la clarification
            # et on s'arrête là pour ce tour — le prochain message du visiteur
            # profitera de cet échange dans l'historique pour mieux répondre.
            # =====================================================================
            timer.start_step("2B_REFORMULATION")
            rephrased_question = await rephrase_question_async(request.question, history)

            if is_clarification_request(rephrased_question):
                clarification = extract_clarification_question(rephrased_question)
                timer.end_step("CLARIFICATION_DEMANDEE")
                yield clarification
                save_interaction(session_id, request.question, clarification, db)
                return
            timer.end_step(f"'{rephrased_question[:60]}'")

            # =====================================================================
            # 3-5. PIPELINE LANGGRAPH
            #   route → [sql_execute ⇄ sql_quality ⇄ table_explore]
            #           [vector | hybrid]
            #         → synthesize
            # Le graphe gère automatiquement la boucle cross-table et le
            # fallback vector si SQL est vide sur toutes les tables.
            # =====================================================================
            timer.start_step("3_5_LANGGRAPH")
            context = ""
            intent = "UNKNOWN"
            sources_count = 0
            standalone_question = request.question
            final_state: dict = {}      # défaut sûr : évite l'UnboundLocalError si le pipeline lève
            pipeline_error = False
            pipeline_error_detail = ""  # vrai détail technique → SMS de diagnostic

            try:
                if RAG_MODE == "agent":
                    final_state = await run_rag_agent(
                        question=request.question,
                        session_id=session_id,
                        history=history,
                        rephrased_question=rephrased_question,
                    )
                else:
                    final_state = await run_rag_graph(
                        question=request.question,
                        session_id=session_id,
                        history=history,
                        rephrased_question=rephrased_question,
                    )
                context           = final_state.get("context", "")
                intent            = final_state.get("intent", "UNKNOWN")
                sources_count     = final_state.get("sources_count", 0)
                standalone_question = final_state.get("rephrased_question", request.question)
                logger.info(f"[{request_id}] 🎯 intent={intent} sources={sources_count} ctx_len={len(context)}")
                timer.end_step(f"intent={intent} sources={sources_count}")
            except Exception as e:
                logger.error(f"[{request_id}] ❌ Erreur LangGraph: {e}")
                logger.error(traceback.format_exc())
                pipeline_error = True
                pipeline_error_detail = _summarize_error(e)
                timer.end_step("ERREUR (contexte vide)")

            # =====================================================================
            # 6. GÉNÉRATION DE LA RÉPONSE (STREAM)
            # =====================================================================
            timer.start_step("6_GENERATION")

            # Fix E — crédits Anthropic épuisés : message UX propre
            if context == "ERREUR_CREDITS":
                yield (
                    "⚠️ Le service IA est temporairement indisponible "
                    "(quota API atteint). Réessaie dans quelques instants "
                    "ou contacte-moi directement sur LinkedIn :)"
                )
                save_interaction(session_id, request.question, "Erreur credits", db)
                timer.end_step("CREDITS_EPUISES")
                return

            # Pipeline LangGraph en échec (ex. modèle indisponible) → message embelli
            # pour le visiteur, MAIS SMS avec le vrai détail technique pour Jordan.
            if pipeline_error:
                yield (
                    "⚠️ Désolé, je rencontre un souci technique côté assistant. "
                    "Réessaie dans un instant — ou contacte-moi directement sur LinkedIn :)"
                )
                save_interaction(session_id, request.question, "Erreur pipeline", db)
                await send_alert_sms(
                    f"PIPELINE KO sess={session_id[:8]} q='{request.question[:60]}' :: {pipeline_error_detail}",
                    level="ERROR",
                )
                timer.end_step("PIPELINE_ERREUR")
                return

            try:
                streamed_answer = ""  # Accumuler la réponse complète

                if RAG_MODE == "agent":
                    agent_answer = final_state.get("answer", "")
                    if not agent_answer:
                        yield "Je n'ai pas trouvé d'informations pertinentes pour répondre à cela."
                        streamed_answer = "Pas d'informations pertinentes."
                    else:
                        words = agent_answer.split(" ")
                        for i, word in enumerate(words):
                            yield word + (" " if i < len(words) - 1 else "")
                            await asyncio.sleep(0.03)
                        streamed_answer = agent_answer
                else:
                    if not context and intent not in ["OFF_TOPIC"]:
                        fallback = "Je n'ai pas trouvé d'informations pertinentes dans mon contexte pour répondre à cela."
                        yield fallback
                        streamed_answer = fallback
                    else:
                        async for token in generate_response(request.question, context, history):
                            yield token
                            streamed_answer += token

                # Sauvegarder la VRAIE réponse en DB
                save_interaction(session_id, request.question, streamed_answer, db)

                timer.end_step("STREAMED")
            except Exception as e:
                logger.error(f"Erreur stream: {e}")
                # Message propre pour l'utilisateur — pas de stack trace
                yield "Désolé, un problème technique est survenu. Réessaie dans un instant."
                # Alerte SMS en arrière-plan avec le vrai contexte technique
                await send_alert_sms(
                    f"Erreur stream session {session_id[:8]}: {_summarize_error(e)}",
                    level="ERROR"
                )

        except Exception as e:
            logger.error(f"[{request_id}] 💥 ERREUR FATALE: {str(e)}")
            logger.error(traceback.format_exc())
            # Message propre — jamais de détails techniques
            yield "Désolé, une erreur inattendue s'est produite. N'hésite pas à réessayer."
            # Alerte SMS urgente
            await send_alert_sms(
                f"CRASH FATAL {request_id}: {_summarize_error(e)}",
                level="ERROR"
            )
        finally:
            db.close()


    return StreamingResponse(event_stream(), media_type="text/plain")


# =============================================================================
# ROUTES D'ADMINISTRATION
# =============================================================================

@app.post("/knowledge/add")
async def add_knowledge(
        requests: List[EmbeddingRequest],
        vs: VectorStoreService = Depends(get_vector_store_service),
        db: Session = Depends(get_db)
):
    """Ajoute des connaissances au vector store"""
    logger.info(f"📥 Ajout de {len(requests)} connaissances")
    from app.Rag.vector_store import EmbeddingRequest as VSEmbeddingRequest

    vs_requests = [
        VSEmbeddingRequest(
            message_text=req.message_text,
            category=req.category,
            metadata=req.metadata
        )
        for req in requests
    ]

    result = await vs.save_infos(vs_requests, db)

    logger.info(f"✅ Connaissances ajoutées: {result}")
    return JSONResponse(content=result)

@app.post("/knowledge/ingest-document")
async def ingest_document(
        file: UploadFile = File(...),
        category: str = Form(...),
        document_type: str = Form("document_uploade"),
        vs: VectorStoreService = Depends(get_vector_store_service),
        db: Session = Depends(get_db)
):
    """
    Ingère un document complet (PDF, DOCX, MD, TXT).

    Le document est :
    1. Parsé pour extraire le texte brut
    2. Découpé en chunks sémantiques via SemanticChunker
    3. Chaque chunk est vectorisé et stocké (vector store + table SQL)

    Args:
        file: Fichier uploadé (multipart)
        category: Catégorie pour le classement (ex: "experience", "projet")
        document_type: Type de document (métadonnée libre)

    Returns:
        Résumé de l'ingestion : nombre de chunks créés, taille du document, etc.
    """
    logger.info(f"📄 Ingestion document: {file.filename} (category={category})")

    # Étape 1 — Lecture du fichier
    file_bytes = await file.read()

    if len(file_bytes) > 10 * 1024 * 1024:  # 10 Mo max
        raise HTTPException(status_code=413, detail="Fichier trop volumineux (max 10 Mo)")

    # Étape 2 — Extraction du texte brut
    try:
        text = load_document(file.filename, file_bytes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    logger.info(f"📄 Texte extrait: {len(text)} caractères")

    # Étape 3 — Chunking sémantique
    chunks = semantic_chunk(text, min_chunk_size=200)
    logger.info(f"📄 {len(chunks)} chunks générés")

    if not chunks:
        raise HTTPException(status_code=400, detail="Aucun chunk généré (document trop court ?)")

    # Étape 4 — Préparation des EmbeddingRequest
    from app.Rag.vector_store import EmbeddingRequest as VSEmbeddingRequest

    vs_requests = []
    for i, chunk in enumerate(chunks):
        vs_requests.append(VSEmbeddingRequest(
            message_text=chunk,
            category=category,
            metadata={
                "source_file": file.filename,
                "chunk_index": i,
                "total_chunks": len(chunks),
                "document_type": document_type,
                "ingestion_method": "semantic_chunker",
            }
        ))

    # Étape 5 — Vectorisation et stockage
    result = await vs.save_infos(vs_requests, db)

    return JSONResponse(content={
        "success": True,
        "filename": file.filename,
        "text_length": len(text),
        "chunks_created": len(chunks),
        "category": category,
        "average_chunk_size": sum(len(c) for c in chunks) // len(chunks),
        "details": result,
    })

@app.get("/stats/")
async def get_stats(db: db_dependency):
    """Statistiques de la base de données"""
    logger.debug("📊 Récupération des stats...")
    try:
        total_embeddings = db.query(models.Embeddings).count()
        total_datas = db.query(models.Datas).count()
        print(total_embeddings, total_datas)

        from sqlalchemy import func
        categories = db.query(
            models.Embeddings.category,
            func.count(models.Embeddings.id)
        ).group_by(models.Embeddings.category).all()

        category_counts = {cat: count for cat, count in categories}

        logger.debug(f"📊 Stats: {total_embeddings} embeddings, {total_datas} datas")

        return {
            "success": True,
            "embeddings": {
                "total": total_embeddings,
                "by_category": category_counts
            },
            "datas": {
                "total": total_datas
            }
        }
    except Exception as e:
        logger.error(f"❌ Erreur stats: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur: {str(e)}")


@app.get("/comments/")
async def get_comments(
        db: db_dependency,
        approved_only: bool = True,
        limit: int = 10
):
    """
    Récupère les témoignages.
    - approved_only=True : (défaut) ne montre que ceux validés (pour le site public).
    - approved_only=False : montre tout (pour l'admin dashboard).
    """
    query = db.query(models.Testimonial)

    if approved_only:
        query = query.filter(models.Testimonial.is_approved == True)

    # Tri par date décroissante (les plus récents en premier)
    return query.order_by(models.Testimonial.created_at.desc()).limit(limit).all()


@app.post("/comments/")
async def add_comment(testimonial: TestimonialCreate, db: db_dependency):
    """Ajoute un nouveau témoignage (non approuvé par défaut)"""
    new_testimonial = models.Testimonial(
        **testimonial.model_dump(),  # Convertit le Pydantic en dict
        is_approved=False,  # Sécurité : toujours false à la création
        is_featured=False
    )
    db.add(new_testimonial)
    db.commit()
    db.refresh(new_testimonial)

    logger.info(f"📝 Nouveau commentaire ajouté par {testimonial.author_name}")
    return new_testimonial


@app.patch("/comments/{comment_id}/status", response_model=TestimonialResponse)
async def update_comment_status(
        comment_id: int,
        status: TestimonialUpdateStatus,
        db: db_dependency
):
    """
    Route Admin pour approuver/rejeter ou mettre en avant un commentaire.
    Envoie juste les champs à modifier (ex: {"is_approved": true})
    """
    comment = db.query(models.Testimonial).filter(models.Testimonial.id == comment_id).first()

    if not comment:
        raise HTTPException(status_code=404, detail="Commentaire non trouvé")

    # Mise à jour partielle
    if status.is_approved is not None:
        comment.is_approved = status.is_approved
        logger.info(f"🔧 Commentaire {comment_id} approuvé: {status.is_approved}")

    if status.is_featured is not None:
        comment.is_featured = status.is_featured

    db.commit()
    db.refresh(comment)
    return comment


@app.delete("/comments/{comment_id}")
async def delete_comment(comment_id: int, db: db_dependency):
    """Supprime un commentaire"""
    comment = db.query(models.Testimonial).filter(models.Testimonial.id == comment_id).first()
    if not comment:
        raise HTTPException(status_code=404, detail="Commentaire non trouvé")

    db.delete(comment)
    db.commit()
    logger.info(f"🗑️ Commentaire {comment_id} supprimé")
    return {"message": "Commentaire supprimé avec succès"}


@app.delete("/clear/{category}")
async def clear_category(category: str, db: db_dependency):
    """Supprimer toutes les entrées d'une catégorie"""
    logger.warning(f"🗑️ Suppression catégorie: {category}")
    try:
        deleted = db.query(models.Embeddings).filter(
            models.Embeddings.category == category
        ).delete()
        db.commit()
        logger.info(f"✅ {deleted} entrées supprimées")
        return {"success": True, "deleted": deleted, "category": category}
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Erreur suppression: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur: {str(e)}")


@app.get("/history/{session_id}")
async def get_history(session_id: str, db: Session = Depends(get_db)):
    """Récupère l'historique d'une session depuis PostgreSQL"""
    history = get_chat_history(session_id, db)
    return {"session_id": session_id, "history": history, "count": len(history)}


@app.delete("/history/{session_id}")
async def clear_history(session_id: str, db: Session = Depends(get_db)):
    """Efface l'historique d'une session dans PostgreSQL"""
    session = db.query(models.ChatSession).filter(
        models.ChatSession.session_id == session_id
    ).first()

    if session:
        db.delete(session)
        db.commit()
        logger.info(f"🗑️ Session {session_id} supprimée de la DB")
    else:
        logger.debug(f"Session {session_id} non trouvée en DB (rien à supprimer)")

    return {"success": True, "message": f"Historique de {session_id} effacé"}


@app.get("/logs/")
async def get_recent_logs():
    """Récupère les dernières lignes de log"""
    try:
        with open('../rag_pipeline.log', 'r', encoding='utf-8') as f:
            lines = f.readlines()[-100:]  # Dernières 100 lignes
        return {"logs": lines}
    except FileNotFoundError:
        return {"logs": [], "message": "Fichier de log non trouvé"}

# =============================================================================
# LANCEMENT
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    logger.info("🚀 Lancement du serveur...")
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
