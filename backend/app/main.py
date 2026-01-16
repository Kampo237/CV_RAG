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
from fastapi import FastAPI, HTTPException, Depends, Request, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from typing import List, Optional, Annotated
from sqlalchemy.orm import Session
from contextlib import asynccontextmanager
import time
import logging
from fastapi.responses import StreamingResponse, JSONResponse
import json
import asyncio
import os
import traceback
import uuid

# =============================================================================
# CONFIGURATION DU LOGGING
# =============================================================================

logger = logging.getLogger("rag_pipeline")
logger.setLevel(logging.DEBUG)

formatter = logging.Formatter(
    '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
console_handler.setFormatter(formatter)

log_path = os.path.join(os.path.dirname(__file__), "rag_pipeline.log")
file_handler = logging.FileHandler(log_path, encoding='utf-8')
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(formatter)

logger.addHandler(console_handler)
logger.addHandler(file_handler)

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
        self.current_step = step_name
        self.step_start = time.time()
        logger.info(f"[{self.request_id}] >> DÉBUT: {step_name}")

    def end_step(self, extra_info: str = ""):
        if self.current_step and self.step_start:
            duration = (time.time() - self.step_start) * 1000
            self.steps[self.current_step] = duration
            info = f" | {extra_info}" if extra_info else ""
            logger.info(f"[{self.request_id}] << FIN: {self.current_step} ({duration:.0f}ms){info}")
            self.current_step = None

    def total_time(self) -> float:
        return (time.time() - self.start_time) * 1000

    def summary(self) -> dict:
        return {
            "request_id": self.request_id,
            "total_ms": round(self.total_time(), 0),
            "steps": {k: round(v, 0) for k, v in self.steps.items()}
        }


# =============================================================================
# IMPORTS LOCAUX (avec fallback pour différents contextes d'exécution)
# =============================================================================

try:
    from app import models
    from app.database import engine, get_db
    from app.Rag import get_intent_router, get_sql_chain, VectorStoreService, get_vector_store_service
    from app.Rag.retrieval import format_context, retrieve_and_rerank
    from app.Rag.generation import rephrase_question_async, generate_response, get_off_topic_response
    from app.Rag.sql_chain import get_sql_chain_raw, check_sql_success
    from app.models import Datas, FAQ, Testimonial, ChatSession, ChatMessage
except ImportError:
    from backend.app import models
    from backend.app.database import engine, get_db
    from backend.app.Rag import get_intent_router, get_sql_chain, VectorStoreService, get_vector_store_service
    from backend.app.Rag.retrieval import format_context, retrieve_and_rerank
    from backend.app.Rag.generation import rephrase_question_async, generate_response, get_off_topic_response
    from backend.app.Rag.sql_chain import get_sql_chain_raw, check_sql_success
    from backend.app.models import Datas, FAQ, Testimonial, ChatSession, ChatMessage

from dotenv import load_dotenv

load_dotenv()


# =============================================================================
# CONFIGURATION FASTAPI
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle: Initialisation au démarrage"""
    logger.info("Démarrage de l'application RAG Chatbot")
    models.Base.metadata.create_all(bind=engine)
    logger.info("Tables créées/vérifiées")
    yield
    logger.info("Arrêt de l'application")


app = FastAPI(
    title="CV Chatbot API",
    description="API RAG pour le portfolio de Yann Willy Jordan Pokam Teguia",
    version="2.0.0",
    lifespan=lifespan
)

# CORS étendu pour le frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://frontend:8000",
        "*"  # À restreindre en production
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# MIDDLEWARE DE LOGGING DES REQUÊTES
# =============================================================================

@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = f"REQ-{int(time.time() * 1000) % 100000}"
    logger.info(f"[{request_id}] >> {request.method} {request.url.path}")
    start_time = time.time()
    response = await call_next(request)
    duration = (time.time() - start_time) * 1000
    status_emoji = "OK" if response.status_code < 400 else "ERR"
    logger.info(f"[{request_id}] << {status_emoji} {response.status_code} ({duration:.0f}ms)")
    return response


# =============================================================================
# MODÈLES PYDANTIC
# =============================================================================

class QuestionRequest(BaseModel):
    question: str
    session_id: Optional[str] = None
    category: Optional[str] = None


class ChatMessageRequest(BaseModel):
    message: str
    session_id: str


class ChatSessionCreate(BaseModel):
    email: EmailStr


class ChatSessionResponse(BaseModel):
    session_id: str
    email: str
    quota_total: int
    quota_remaining: int
    messages: List[dict] = []


class TestimonialCreate(BaseModel):
    author_name: str
    author_email: EmailStr
    author_company: Optional[str] = None
    author_position: Optional[str] = None
    content: str
    rating: int = 5


class TestimonialResponse(BaseModel):
    id: int
    author_name: str
    author_company: Optional[str]
    author_position: Optional[str]
    content: str
    rating: int
    is_featured: bool
    created_at: str

    class Config:
        from_attributes = True


class EmbeddingRequest(BaseModel):
    message_text: str
    category: str
    metadata: dict = {}


class FAQBase(BaseModel):
    question: str
    reponse: str
    variantes: Optional[List[str]] = []
    categorie: str
    icone: Optional[str] = "?"
    ordre_affichage: Optional[int] = 0


class FAQCreate(FAQBase):
    pass


class FAQUpdate(BaseModel):
    question: Optional[str] = None
    reponse: Optional[str] = None
    variantes: Optional[List[str]] = None
    categorie: Optional[str] = None
    icone: Optional[str] = None
    ordre_affichage: Optional[int] = None
    est_active: Optional[bool] = None


class FAQResponse(FAQBase):
    id: int
    vues: int
    est_active: bool

    class Config:
        from_attributes = True


class FAQListResponse(BaseModel):
    total: int
    categories: dict
    faqs: List[FAQResponse]


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
        logger.debug("Router initialisé")
    return _router


def get_sql():
    global _sql_chain
    if _sql_chain is None:
        logger.debug("Initialisation de la chaîne SQL...")
        _sql_chain = get_sql_chain()
        logger.debug("Chaîne SQL initialisée")
    return _sql_chain


# =============================================================================
# STOCKAGE D'HISTORIQUE (en mémoire - fallback si pas de session DB)
# =============================================================================

_chat_history: dict[str, List[dict]] = {}
_request_counts: dict[str, int] = {}
MAX_REQUESTS_PER_SESSION = 50


def get_chat_history(session_id: str) -> List[dict]:
    history = _chat_history.get(session_id, [])
    logger.debug(f"Historique récupéré: {len(history)} messages")
    return history


def save_interaction(session_id: str, question: str, answer: str):
    if session_id not in _chat_history:
        _chat_history[session_id] = []
    _chat_history[session_id].append({"role": "user", "content": question})
    _chat_history[session_id].append({"role": "assistant", "content": answer})
    if len(_chat_history[session_id]) > 20:
        _chat_history[session_id] = _chat_history[session_id][-20:]
    logger.debug(f"Interaction sauvegardée pour session {session_id}")


def check_rate_limit(session_id: str) -> bool:
    if not session_id:
        return True
    count = _request_counts.get(session_id, 0)
    if count >= MAX_REQUESTS_PER_SESSION:
        logger.warning(f"Rate limit atteint pour session {session_id}")
        return False
    _request_counts[session_id] = count + 1
    return True


# =============================================================================
# ROUTES PRINCIPALES
# =============================================================================

@app.get("/")
async def root():
    return {"message": "CV Chatbot API", "status": "online", "version": "2.0.0"}


# =============================================================================
# ENDPOINTS CHAT SESSION (pour le frontend)
# =============================================================================

@app.post("/api/chat/session", response_model=ChatSessionResponse)
async def create_chat_session(data: ChatSessionCreate, db: db_dependency):
    """Crée ou récupère une session de chat pour un email"""
    logger.info(f"Création/récupération session pour: {data.email}")

    # Chercher une session existante
    existing = db.query(ChatSession).filter(
        ChatSession.email == data.email,
        ChatSession.is_active == True
    ).first()

    if existing:
        logger.debug(f"Session existante trouvée: {existing.session_id}")
        messages = [msg.to_dict() for msg in existing.messages[-20:]]
        return ChatSessionResponse(
            session_id=existing.session_id,
            email=existing.email,
            quota_total=existing.quota_total,
            quota_remaining=existing.quota_remaining,
            messages=messages
        )

    # Créer une nouvelle session
    new_session = ChatSession(
        session_id=f"sess_{uuid.uuid4().hex[:16]}",
        email=data.email,
        quota_total=50,
        quota_used=0
    )
    db.add(new_session)
    db.commit()
    db.refresh(new_session)

    logger.info(f"Nouvelle session créée: {new_session.session_id}")

    return ChatSessionResponse(
        session_id=new_session.session_id,
        email=new_session.email,
        quota_total=new_session.quota_total,
        quota_remaining=new_session.quota_remaining,
        messages=[]
    )


@app.post("/api/chat/message")
async def chat_message(data: ChatMessageRequest, db: db_dependency):
    """
    Endpoint de chat compatible avec le frontend.
    Renvoie une réponse en streaming.
    """
    logger.info(f"Message reçu - Session: {data.session_id}")

    # Vérifier la session
    session = db.query(ChatSession).filter(
        ChatSession.session_id == data.session_id
    ).first()

    if not session:
        # Créer une session anonyme si non trouvée
        logger.warning(f"Session non trouvée, création anonyme")
        session = ChatSession(
            session_id=data.session_id,
            email="anonymous@portfolio.local",
            quota_total=50,
            quota_used=0
        )
        db.add(session)
        db.commit()

    # Vérifier le quota
    if session.quota_remaining <= 0:
        raise HTTPException(status_code=429, detail="Quota épuisé")

    # Incrémenter l'usage
    session.quota_used += 1
    db.commit()

    # Créer la requête pour le pipeline RAG
    request = QuestionRequest(
        question=data.message,
        session_id=data.session_id
    )

    # Retourner le stream
    return await chat(request)


# =============================================================================
# ROUTE CHAT PRINCIPALE (RAG Pipeline)
# =============================================================================

@app.post("/chat/")
async def chat(request: QuestionRequest):
    """Pipeline complet RAG avec streaming et métadonnées finales."""

    async def event_stream():
        request_id = f"CHAT-{int(time.time() * 1000) % 100000}"
        timer = PipelineTimer(request_id)

        logger.info("=" * 60)
        logger.info(f"[{request_id}] NOUVELLE QUESTION: {request.question[:100]}...")
        logger.info("=" * 60)

        try:
            session_id = request.session_id or "anonymous"

            # 1. RATE LIMITING
            timer.start_step("1_RATE_LIMITING")
            if not check_rate_limit(session_id):
                timer.end_step("BLOCKED")
                raise HTTPException(status_code=429, detail="Limite de requêtes atteinte.")
            timer.end_step("OK")

            # 2. RÉCUPÉRATION HISTORIQUE
            timer.start_step("2_HISTORIQUE")
            history = get_chat_history(session_id)
            timer.end_step(f"{len(history)} messages")

            # 3. REFORMULATION
            timer.start_step("3_REFORMULATION")
            try:
                standalone_question = await rephrase_question_async(request.question, history)
                timer.end_step("OK")
            except Exception as e:
                logger.error(f"[{request_id}] Erreur reformulation: {str(e)}")
                standalone_question = request.question
                timer.end_step("FALLBACK")

            # 4. ROUTAGE SÉMANTIQUE
            timer.start_step("4_ROUTAGE")
            try:
                router_chain = get_router()
                intent = await router_chain.ainvoke({"question": standalone_question})
                intent = intent.strip().upper()
                logger.info(f"[{request_id}] INTENT: {intent}")
                timer.end_step(f"intent={intent}")
            except Exception as e:
                logger.error(f"[{request_id}] Erreur routage: {str(e)}")
                intent = "VECTOR"
                timer.end_step("FALLBACK VECTOR")

            # 5. TRAITEMENT SELON INTENT
            context = ""
            sources_count = 0
            fallback_to_vector = False

            # OFF_TOPIC
            if intent == "OFF_TOPIC":
                timer.start_step("5_OFF_TOPIC")
                answer = get_off_topic_response()
                timer.end_step()
                save_interaction(session_id, request.question, answer)

                for char in answer:
                    yield char

                metadata = {
                    "intent": intent,
                    "sources_count": 0,
                    "debug": timer.summary()
                }
                yield f"__METADATA__{json.dumps(metadata)}"
                return

            # SQL
            elif intent == "SQL":
                timer.start_step("5_SQL_CHAIN")
                try:
                    sql_chain = get_sql()
                    sql_result = await sql_chain.ainvoke({"question": standalone_question})

                    if check_sql_success(sql_result):
                        context = sql_result
                        sources_count = 1
                        timer.end_step("SUCCESS")
                    else:
                        timer.end_step("FAILED")
                        fallback_to_vector = True
                except Exception as e:
                    logger.warning(f"[{request_id}] SQL crash: {e}")
                    timer.end_step("CRASH")
                    fallback_to_vector = True

                if fallback_to_vector:
                    intent = "SQL->VECTOR"

            # VECTOR_SQL (Hybride)
            elif intent == "VECTOR_SQL":
                timer.start_step("5_HYBRID")
                try:
                    sql_raw = get_sql_chain_raw()
                    sql_result = await sql_raw.ainvoke({"question": standalone_question})

                    vs_service = get_vector_store_service()
                    refined_docs = await retrieve_and_rerank(standalone_question, vs_service, 10, 2)
                    vector_context = format_context(refined_docs)

                    context = f"Données SQL:\n{sql_result}\n\nContexte:\n{vector_context}"
                    sources_count = len(refined_docs) + 1
                    timer.end_step("OK")
                except Exception as e:
                    logger.warning(f"[{request_id}] Hybrid crash: {e}")
                    timer.end_step("CRASH")
                    fallback_to_vector = True

            # VECTOR ou fallback
            elif intent == "VECTOR":
                fallback_to_vector = True
            else:
                logger.warning(f"[{request_id}] Intent inconnu '{intent}'")
                fallback_to_vector = True

            # 5b. VECTOR SEARCH
            if fallback_to_vector:
                timer.start_step("5_VECTOR_SEARCH")
                try:
                    vs_service = get_vector_store_service()
                    refined_docs = await retrieve_and_rerank(
                        query=standalone_question,
                        vector_store_service=vs_service,
                        initial_k=5,
                        final_k=3
                    )
                    context = format_context(refined_docs)
                    sources_count = len(refined_docs)
                    timer.end_step(f"docs={len(refined_docs)}")
                except Exception as e:
                    logger.error(f"[{request_id}] VECTOR failed: {e}")
                    timer.end_step("FAILED")
                    context = ""

            # 6. GÉNÉRATION
            timer.start_step("6_GENERATION")
            full_response = ""

            try:
                if not context:
                    msg = "Je n'ai pas trouvé d'informations pertinentes pour répondre à cette question."
                    yield msg
                    full_response = msg
                else:
                    async for token in generate_response(request.question, context, history):
                        yield token
                        full_response += token

                metadata = {
                    "intent": intent,
                    "sources_count": sources_count,
                    "debug": timer.summary()
                }
                yield f"__METADATA__{json.dumps(metadata)}"

                save_interaction(session_id, request.question, full_response)
                timer.end_step("STREAMED")

            except Exception as e:
                logger.error(f"Erreur stream: {e}")
                yield f"\n[Erreur: {str(e)}]"

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"[{request_id}] ERREUR FATALE: {str(e)}")
            logger.error(traceback.format_exc())
            yield f"\n[Erreur interne]"

    return StreamingResponse(event_stream(), media_type="text/plain")


# =============================================================================
# ENDPOINTS TESTIMONIALS
# =============================================================================

testimonials_router = APIRouter(prefix="/api/testimonials", tags=["Testimonials"])


@testimonials_router.get("/")
async def get_testimonials(db: db_dependency, featured_only: bool = False):
    """Récupère les témoignages approuvés"""
    query = db.query(Testimonial).filter(Testimonial.is_approved == True)

    if featured_only:
        query = query.filter(Testimonial.is_featured == True)

    testimonials = query.order_by(Testimonial.created_at.desc()).all()

    return {
        "total": len(testimonials),
        "testimonials": [t.to_dict() for t in testimonials]
    }


@testimonials_router.post("/")
async def create_testimonial(data: TestimonialCreate, db: db_dependency):
    """Crée un nouveau témoignage (en attente d'approbation)"""
    logger.info(f"Nouveau témoignage de: {data.author_name}")

    testimonial = Testimonial(
        author_name=data.author_name,
        author_email=data.author_email,
        author_company=data.author_company,
        author_position=data.author_position,
        content=data.content,
        rating=max(1, min(5, data.rating)),
        is_approved=False,
        is_featured=False
    )

    db.add(testimonial)
    db.commit()
    db.refresh(testimonial)

    logger.info(f"Témoignage créé: ID {testimonial.id}")

    return {
        "success": True,
        "message": "Merci pour votre témoignage ! Il sera publié après modération.",
        "id": testimonial.id
    }


@testimonials_router.get("/pending")
async def get_pending_testimonials(db: db_dependency):
    """Récupère les témoignages en attente (admin)"""
    testimonials = db.query(Testimonial).filter(
        Testimonial.is_approved == False
    ).order_by(Testimonial.created_at.desc()).all()

    return {
        "total": len(testimonials),
        "testimonials": [t.to_dict(include_email=True) for t in testimonials]
    }


@testimonials_router.put("/{testimonial_id}/approve")
async def approve_testimonial(testimonial_id: int, db: db_dependency, featured: bool = False):
    """Approuve un témoignage (admin)"""
    testimonial = db.query(Testimonial).filter(Testimonial.id == testimonial_id).first()

    if not testimonial:
        raise HTTPException(status_code=404, detail="Témoignage non trouvé")

    testimonial.is_approved = True
    testimonial.is_featured = featured
    db.commit()

    return {"success": True, "message": "Témoignage approuvé"}


@testimonials_router.delete("/{testimonial_id}")
async def delete_testimonial(testimonial_id: int, db: db_dependency):
    """Supprime un témoignage (admin)"""
    testimonial = db.query(Testimonial).filter(Testimonial.id == testimonial_id).first()

    if not testimonial:
        raise HTTPException(status_code=404, detail="Témoignage non trouvé")

    db.delete(testimonial)
    db.commit()

    return {"success": True, "message": "Témoignage supprimé"}


app.include_router(testimonials_router)


# =============================================================================
# ENDPOINTS FAQ
# =============================================================================

faq_router = APIRouter(prefix="/faq", tags=["FAQ"])


@faq_router.get("/", response_model=FAQListResponse)
def get_all_faqs(categorie: Optional[str] = None, db: Session = Depends(get_db)):
    """Récupère toutes les FAQ actives"""
    query = db.query(FAQ).filter(FAQ.est_active == True)

    if categorie:
        query = query.filter(FAQ.categorie == categorie)

    faqs = query.order_by(FAQ.ordre_affichage, FAQ.id).all()

    categories = {}
    for faq in faqs:
        if faq.categorie not in categories:
            categories[faq.categorie] = []
        categories[faq.categorie].append(faq.to_dict())

    return {"total": len(faqs), "categories": categories, "faqs": faqs}


@faq_router.get("/{faq_id}", response_model=FAQResponse)
def get_faq(faq_id: int, db: Session = Depends(get_db)):
    """Récupère une FAQ par ID"""
    faq = db.query(FAQ).filter(FAQ.id == faq_id).first()
    if not faq:
        raise HTTPException(status_code=404, detail="FAQ non trouvée")
    faq.increment_vues(db)
    return faq


@faq_router.post("/", response_model=FAQResponse)
def create_faq(faq_data: FAQCreate, db: Session = Depends(get_db)):
    """Crée une FAQ"""
    new_faq = FAQ(**faq_data.dict())
    db.add(new_faq)
    db.commit()
    db.refresh(new_faq)
    return new_faq


@faq_router.put("/{faq_id}", response_model=FAQResponse)
def update_faq(faq_id: int, faq_data: FAQUpdate, db: Session = Depends(get_db)):
    """Met à jour une FAQ"""
    faq = db.query(FAQ).filter(FAQ.id == faq_id).first()
    if not faq:
        raise HTTPException(status_code=404, detail="FAQ non trouvée")

    for key, value in faq_data.dict(exclude_unset=True).items():
        setattr(faq, key, value)

    db.commit()
    db.refresh(faq)
    return faq


@faq_router.delete("/{faq_id}")
def delete_faq(faq_id: int, db: Session = Depends(get_db)):
    """Désactive une FAQ"""
    faq = db.query(FAQ).filter(FAQ.id == faq_id).first()
    if not faq:
        raise HTTPException(status_code=404, detail="FAQ non trouvée")

    faq.est_active = False
    db.commit()
    return {"message": "FAQ désactivée"}


@faq_router.get("/search/{query}")
def search_faq(query: str, db: Session = Depends(get_db)):
    """Recherche dans les FAQ"""
    faqs = db.query(FAQ).filter(
        FAQ.est_active == True,
        FAQ.question.ilike(f"%{query}%")
    ).all()
    return {"results": [faq.to_dict() for faq in faqs]}


app.include_router(faq_router)


# =============================================================================
# ENDPOINTS PROJETS (depuis la table datas)
# =============================================================================

@app.get("/api/projects")
async def get_projects(db: db_dependency):
    """Récupère les projets depuis la table datas"""
    projects = db.query(Datas).filter(Datas.category == "projet").all()
    return {
        "total": len(projects),
        "projects": [p.to_dict() for p in projects]
    }


@app.get("/api/projects/{project_id}")
async def get_project(project_id: int, db: db_dependency):
    """Récupère un projet par ID"""
    project = db.query(Datas).filter(
        Datas.id == project_id,
        Datas.category == "projet"
    ).first()

    if not project:
        raise HTTPException(status_code=404, detail="Projet non trouvé")

    return project.to_dict()


# =============================================================================
# ENDPOINTS COMPÉTENCES
# =============================================================================

@app.get("/api/skills")
async def get_skills(db: db_dependency):
    """Récupère les compétences depuis la table datas"""
    skills = db.query(Datas).filter(Datas.category == "competence").all()
    return {
        "total": len(skills),
        "skills": [s.to_dict() for s in skills]
    }


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
    logger.info(f"Ajout de {len(requests)} connaissances")

    try:
        from app.Rag.vector_store import EmbeddingRequest as VSEmbeddingRequest
    except ImportError:
        from backend.app.Rag.vector_store import EmbeddingRequest as VSEmbeddingRequest

    vs_requests = [
        VSEmbeddingRequest(
            message_text=req.message_text,
            category=req.category,
            metadata=req.metadata
        )
        for req in requests
    ]

    result = await vs.save_infos(vs_requests, db)
    logger.info(f"Connaissances ajoutées: {result}")
    return JSONResponse(content=result)


@app.get("/stats/")
async def get_stats(db: db_dependency):
    """Statistiques de la base de données"""
    try:
        total_datas = db.query(Datas).count()
        total_faq = db.query(FAQ).count()
        total_testimonials = db.query(Testimonial).count()
        total_sessions = db.query(ChatSession).count()

        from sqlalchemy import func
        categories = db.query(
            Datas.category,
            func.count(Datas.id)
        ).group_by(Datas.category).all()

        return {
            "success": True,
            "datas": {"total": total_datas, "by_category": {c: n for c, n in categories}},
            "faq": {"total": total_faq},
            "testimonials": {"total": total_testimonials},
            "chat_sessions": {"total": total_sessions}
        }
    except Exception as e:
        logger.error(f"Erreur stats: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/clear/{category}")
async def clear_category(category: str, db: db_dependency):
    """Supprimer toutes les entrées d'une catégorie"""
    logger.warning(f"Suppression catégorie: {category}")
    try:
        deleted = db.query(Datas).filter(Datas.category == category).delete()
        db.commit()
        return {"success": True, "deleted": deleted, "category": category}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/history/{session_id}")
async def get_history(session_id: str = "anonymous"):
    """Récupère l'historique d'une session"""
    history = get_chat_history(session_id)
    return {"session_id": session_id, "history": history, "count": len(history)}


@app.delete("/history/{session_id}")
async def clear_history(session_id: str):
    """Efface l'historique d'une session"""
    if session_id in _chat_history:
        del _chat_history[session_id]
    return {"success": True, "message": f"Historique de {session_id} effacé"}


# =============================================================================
# LANCEMENT
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    logger.info("Lancement du serveur...")
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
