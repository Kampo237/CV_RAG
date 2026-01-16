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
from pydantic import BaseModel
from typing import List, Optional, Annotated
from sqlalchemy.orm import Session
from contextlib import asynccontextmanager
import time
import logging
from fastapi.responses import StreamingResponse, JSONResponse
import json
import asyncio
import os, traceback

# =============================================================================
# CONFIGURATION DU LOGGING
# =============================================================================

# Créer un logger personnalisé
logger = logging.getLogger("rag_pipeline")
logger.setLevel(logging.DEBUG)

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

from backend.app import models
from backend.app.database import engine, get_db

# Imports RAG
from backend.app.Rag import (
    get_intent_router,
    get_sql_chain,
    VectorStoreService,
    get_vector_store_service
)
from backend.app.Rag.retrieval import format_context, retrieve_and_rerank
from backend.app.Rag.generation import (
    rephrase_question_async,
    generate_response,
    get_off_topic_response

)
from backend.app.Rag.sql_chain import get_sql_chain_raw


from dotenv import load_dotenv

load_dotenv()


# =============================================================================
# CONFIGURATION FASTAPI
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle: Initialisation au démarrage"""
    logger.info("🚀 Démarrage de l'application RAG Chatbot")
    models.Base.metadata.create_all(bind=engine)
    logger.info("✅ Tables créées/vérifiées")
    yield
    logger.info("👋 Arrêt de l'application")


app = FastAPI(
    title="CV Chatbot API",
    description="API RAG pour le portfolio de Yann Willy Jordan Pokam Teguia",
    version="1.0.0",
    lifespan=lifespan
)

# CORS pour le frontend Django
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
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

class FAQBase(BaseModel):
    question: str
    reponse: str
    variantes: Optional[List[str]] = []
    categorie: str
    icone: Optional[str] = "❓"
    ordre_affichage: Optional[int] = 0


class FAQCreate(FAQBase):
    """Schéma pour créer une FAQ"""
    pass


class FAQUpdate(BaseModel):
    """Schéma pour mettre à jour une FAQ"""
    question: Optional[str] = None
    reponse: Optional[str] = None
    variantes: Optional[List[str]] = None
    categorie: Optional[str] = None
    icone: Optional[str] = None
    ordre_affichage: Optional[int] = None
    est_active: Optional[bool] = None


class FAQResponse(FAQBase):
    """Schéma de réponse"""
    id: int
    vues: int
    est_active: bool

    class Config:
        from_attributes = True


class FAQListResponse(BaseModel):
    """Liste de FAQ groupées par catégorie"""
    total: int
    categories: dict  # {"identite": [...], "contact": [...]}
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
# STOCKAGE D'HISTORIQUE
# =============================================================================

_chat_history: dict[str, List[dict]] = {}


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


# =============================================================================
# RATE LIMITING
# =============================================================================

_request_counts: dict[str, int] = {}
MAX_REQUESTS_PER_SESSION = 50


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
# ROUTE PRINCIPALE - CHAT AVEC LOGS DÉTAILLÉS
# =============================================================================

@app.get("/")
async def root():
    return {"message": "Salut chef 👋", "status": "online"}


@app.post("/chat/")
async def chat(request: QuestionRequest):
    """
    Pipeline complet RAG avec streaming et métadonnées finales.
    """

    async def event_stream():
        request_id = f"CHAT-{int(time.time() * 1000) % 100000}"
        timer = PipelineTimer(request_id)

        logger.info("=" * 60)
        logger.info(f"[{request_id}] 🎤 NOUVELLE QUESTION: {request.question[:100]}...")
        logger.info("=" * 60)

        try:
            session_id = request.session_id or "anonymous"
            logger.debug(f"[{request_id}] Session ID: {session_id}")

            # =====================================================================
            # 1. RATE LIMITING
            # =====================================================================
            timer.start_step("1_RATE_LIMITING")
            if not check_rate_limit(session_id):
                timer.end_step("BLOCKED")
                raise HTTPException(status_code=429, detail="Limite de requêtes atteinte.")
            timer.end_step("OK")

            # =====================================================================
            # 2. RÉCUPÉRATION HISTORIQUE
            # =====================================================================
            timer.start_step("2_HISTORIQUE")
            history = get_chat_history(session_id)
            timer.end_step(f"{len(history)} messages")

            # =====================================================================
            # 3. REFORMULATION
            # =====================================================================
            timer.start_step("3_REFORMULATION")
            try:
                standalone_question = await rephrase_question_async(request.question, history)
                timer.end_step("OK")
            except Exception as e:
                logger.error(f"[{request_id}] ❌ Erreur reformulation: {str(e)}")
                logger.error(traceback.format_exc())
                standalone_question = request.question
                timer.end_step("FALLBACK (erreur)")

            # =====================================================================
            # 4. ROUTAGE SÉMANTIQUE
            # =====================================================================
            timer.start_step("4_ROUTAGE")
            try:
                router_chain = get_router()
                intent = await router_chain.ainvoke({"question": standalone_question})
                intent = intent.strip().upper()
                logger.info(f"[{request_id}] 🎯 INTENT DÉTECTÉ: {intent}")
                timer.end_step(f"intent={intent}")
            except Exception as e:
                logger.error(f"[{request_id}] ❌ Erreur routage: {str(e)}")
                logger.error(traceback.format_exc())
                raise

            # =====================================================================
            # 5. TRAITEMENT SELON INTENT
            # =====================================================================

            context = ""
            sources_count = 0

            # On utilise un drapeau pour savoir si on doit passer au fallback
            fallback_to_vector = False

            try:
                # ----- OFF_TOPIC -----
                if intent == "OFF_TOPIC":
                    timer.start_step("5_OFF_TOPIC")
                    answer = get_off_topic_response()
                    timer.end_step()

                    # On stream la réponse statique tout de suite
                    # Note: Pour être cohérent avec le reste, on pourrait juste set le context
                    # Mais comme c'est une réponse toute faite, on la traite ici.
                    save_interaction(session_id, request.question, answer)

                    # Stream caractère par caractère pour l'effet
                    for char in answer:
                        yield char

                    # Fin propre
                    metadata = {
                        "intent": intent,
                        "sources_count": 0,
                        "debug": timer.summary()
                    }
                    yield f"__METADATA__{json.dumps(metadata)}"
                    return  # <--- On sort de la fonction ici

                # ----- SQL intent -----
                elif intent == "SQL":
                    timer.start_step("5_SQL_CHAIN")
                    try:
                        sql_chain = get_sql()
                        # On récupère le résultat SQL
                        sql_result = await sql_chain.ainvoke({"question": standalone_question})

                        from backend.app.Rag.sql_chain import check_sql_success
                        if check_sql_success(sql_result):
                            context = sql_result
                            sources_count = 1
                            timer.end_step("SUCCESS")
                        else:
                            timer.end_step("FAILED (empty/error)")
                            fallback_to_vector = True

                    except Exception as e:
                        logger.warning(f"[{request_id}] ⚠️ SQL crash: {e}")
                        timer.end_step("CRASH")
                        fallback_to_vector = True

                    if fallback_to_vector:
                        intent = "SQL→VECTOR"  # On met à jour l'intent pour le debug

                # ----- VECTOR_SQL (Hybride) -----
                elif intent == "VECTOR_SQL":
                    timer.start_step("5_HYBRID")
                    try:
                        # 1. SQL en parallèle ou séquentiel
                        sql_raw = get_sql_chain_raw()
                        sql_result = await sql_raw.ainvoke({"question": standalone_question})

                        # 2. Vector
                        vs_service = get_vector_store_service()
                        refined_docs = await retrieve_and_rerank(
                            standalone_question, vs_service, 10, 2
                        )
                        vector_context = format_context(refined_docs)

                        context = (
                            f"Données structurées (SQL):\n{sql_result}\n\n"
                            f"Contexte documentaire:\n{vector_context}"
                        )
                        sources_count = len(refined_docs) + 1
                        timer.end_step("OK")
                    except Exception as e:
                        logger.warning(f"[{request_id}] ⚠️ Hybrid crash: {e}")
                        timer.end_step("CRASH")
                        fallback_to_vector = True

                # ----- VECTOR (Cas explicite) -----
                elif intent == "VECTOR":
                    fallback_to_vector = True  # On utilise la logique commune ci-dessous

                # ----- Cas par défaut (Intent inconnu) -----
                else:
                    logger.warning(f"[{request_id}] Intent inconnu '{intent}', fallback Vector")
                    fallback_to_vector = True

            except Exception as global_e:
                logger.error(f"[{request_id}] 💥 Erreur majeure dans l'étape 5: {global_e}")
                fallback_to_vector = True

            # =====================================================================
            # 5b. LOGIQUE COMMUNE VECTOR (Fallback ou Intent direct)
            # =====================================================================
            if fallback_to_vector:
                timer.start_step("5_VECTOR_SEARCH")
                try:
                    vs_service = get_vector_store_service()
                    # On cherche un peu plus large (5) et on rerank (3)
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
                    logger.error(f"[{request_id}] ❌ VECTOR Search failed: {e}")
                    timer.end_step("FAILED")
                    context = ""  # Pas de contexte, le LLM improvisera

            # =====================================================================
            # 6. GÉNÉRATION DE LA RÉPONSE (STREAM)
            # =====================================================================
            timer.start_step("6_GENERATION")

            try:
                if not context and intent not in ["OFF_TOPIC"]:
                    yield "Je n'ai pas trouvé d'informations pertinentes dans mon contexte pour répondre à cela."

                elif intent == "OFF_TOPIC":
                    # Si c'est off_topic, on stream la réponse pré-faite
                    for word in get_off_topic_response().split(" "):
                        yield word + " "
                        await asyncio.sleep(0.05)  # Petit effet de style

                else:
                    # On laisse passer les tokens du générateur directement
                    async for token in generate_response(request.question, context, history):
                        yield token

                # 7. METADATA FINALE (Le séparateur magique)
                metadata = {
                    "intent": intent,
                    "sources_count": sources_count,
                    "debug": timer.summary()
                }

                yield f"__METADATA__{json.dumps(metadata)}"

                save_interaction(session_id, request.question, "Réponse streamée")

                timer.end_step("STREAMED")
            except Exception as e:
                logger.error(f"Erreur stream: {e}")
                yield f"\n[Erreur interne: {str(e)}]"

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"[{request_id}] 💥 ERREUR FATALE: {str(e)}")
            logger.error(traceback.format_exc())
            yield f"\n[Erreur interne: {str(e)}]"
            raise


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

    logger.info(f"✅ Connaissances ajoutées: {result}")
    return JSONResponse(content=result)


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


router = APIRouter(prefix="/faq", tags=["FAQ"])

@router.get("/", response_model=FAQListResponse)
def get_all_faqs(
        categorie: Optional[str] = None,
        db: Session = Depends(get_db)
):
    '''Récupère toutes les FAQ actives, optionnellement filtrées par catégorie'''
    query = db.query(FAQ).filter(FAQ.est_active == True)

    if categorie:
        query = query.filter(FAQ.categorie == categorie)

    faqs = query.order_by(FAQ.ordre_affichage, FAQ.id).all()

    # Grouper par catégorie
    categories = {}
    for faq in faqs:
        if faq.categorie not in categories:
            categories[faq.categorie] = []
        categories[faq.categorie].append(faq.to_dict())

    return {
        "total": len(faqs),
        "categories": categories,
        "faqs": faqs
    }


@router.get("/{faq_id}", response_model=FAQResponse)
def get_faq(faq_id: int, db: Session = Depends(get_db)):
    '''Récupère une FAQ par son ID et incrémente le compteur de vues'''
    faq = db.query(FAQ).filter(FAQ.id == faq_id).first()
    if not faq:
        raise HTTPException(status_code=404, detail="FAQ non trouvée")

    # Incrémenter les vues
    faq.increment_vues(db)

    return faq


@router.post("/", response_model=FAQResponse)
def create_faq(faq_data: FAQCreate, db: Session = Depends(get_db)):
    '''Crée une nouvelle FAQ'''
    new_faq = FAQ(**faq_data.dict())
    db.add(new_faq)
    db.commit()
    db.refresh(new_faq)
    return new_faq


@router.put("/{faq_id}", response_model=FAQResponse)
def update_faq(faq_id: int, faq_data: FAQUpdate, db: Session = Depends(get_db)):
    '''Met à jour une FAQ'''
    faq = db.query(FAQ).filter(FAQ.id == faq_id).first()
    if not faq:
        raise HTTPException(status_code=404, detail="FAQ non trouvée")

    for key, value in faq_data.dict(exclude_unset=True).items():
        setattr(faq, key, value)

    db.commit()
    db.refresh(faq)
    return faq


@router.delete("/{faq_id}")
def delete_faq(faq_id: int, db: Session = Depends(get_db)):
    '''Désactive une FAQ (soft delete)'''
    faq = db.query(FAQ).filter(FAQ.id == faq_id).first()
    if not faq:
        raise HTTPException(status_code=404, detail="FAQ non trouvée")

    faq.est_active = False
    db.commit()
    return {"message": "FAQ désactivée"}


@router.get("/search/{query}")
def search_faq(query: str, db: Session = Depends(get_db)):
    '''Recherche dans les questions et variantes'''
    faqs = db.query(FAQ).filter(
        FAQ.est_active == True,
        (
                FAQ.question.ilike(f"%{query}%") |
                FAQ.variantes.contains([query])
        )
    ).all()

    return {"results": [faq.to_dict() for faq in faqs]}


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
async def get_history(session_id: str = "anonymous"):
    """Récupère l'historique d'une session"""
    history = get_chat_history(session_id)
    return {"session_id": session_id, "history": history, "count": len(history)}


@app.delete("/history/{session_id}")
async def clear_history(session_id: str):
    """Efface l'historique d'une session"""
    if session_id in _chat_history:
        del _chat_history[session_id]
    logger.info(f"🗑️ Historique effacé: {session_id}")
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
