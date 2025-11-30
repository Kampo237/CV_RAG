"""
Chainlit UI - Interface de test pour le RAG Chatbot CV

Ce fichier crée une interface de chat qui communique avec ton API FastAPI.
Tu peux l'utiliser localement pour tester, puis le déployer sur Chainlit Cloud.

Installation:
    pip install chainlit httpx

Lancement:
    chainlit run chainlit_app.py -w

Configuration:
    Modifier API_BASE_URL pour pointer vers ton API (local ou déployée)
"""

import chainlit as cl
import httpx
import uuid
from typing import Optional
import time, asyncio, random


# =============================================================================
# CONFIGURATION
# =============================================================================

# URL de ton API FastAPI
# Local: "http://localhost:8001"
# Déployé: "https://ton-api.railway.app" ou "https://ec2-xx-xx-xx.amazonaws.com:8001"
API_BASE_URL = "http://api:8001"

# Timeout pour les requêtes (le RAG peut prendre du temps)
REQUEST_TIMEOUT = 60.0

MIN_DELAY = 0.005  # 20ms
MAX_DELAY = 0.02  # 50ms
CHUNK_PAUSE = 0.5  # 200ms après ponctuation

MAX_RETRIES = 3
HEARTBEAT_INTERVAL = 10


# =============================================================================
# FONCTIONS UTILITAIRES
# =============================================================================

async def call_chat_api(question: str, session_id: str) -> dict:
    """
    Appelle l'endpoint /chat/ de ton API FastAPI

    Args:
        question: La question de l'utilisateur
        session_id: ID de session pour l'historique

    Returns:
        dict avec answer, intent, sources_count, debug
    """
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        try:
            response = await client.post(
                f"{API_BASE_URL}/chat/",
                json={
                    "question": question,
                    "session_id": session_id
                }
            )
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException:
            return {
                "answer": "⏱️ La requête a pris trop de temps. Réessaie!",
                "intent": "ERROR",
                "sources_count": 0
            }
        except httpx.HTTPStatusError as e:
            return {
                "answer": f"❌ Erreur API: {e.response.status_code}",
                "intent": "ERROR",
                "sources_count": 0
            }
        except Exception as e:
            return {
                "answer": f"❌ Erreur de connexion: {str(e)}",
                "intent": "ERROR",
                "sources_count": 0
            }


async def check_api_health() -> bool:
    """Vérifie si l'API est accessible"""
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            response = await client.get(f"{API_BASE_URL}/")
            return response.status_code == 200
        except:
            return False


# =============================================================================
# CHAINLIT HANDLERS
# =============================================================================

@cl.on_chat_start
async def on_chat_start():
    """
    Appelé au démarrage d'une nouvelle conversation
    """
    import random

    # Configuration de l'animation
    MIN_DELAY = 0.01  # 10ms
    MAX_DELAY = 0.03  # 30ms
    PAUSE_PUNCTUATION = 0.15  # Pause après ponctuation
    PAUSE_NEWLINE = 0.2  # Pause après saut de ligne

    # Générer un ID de session unique
    session_id = str(uuid.uuid4())
    cl.user_session.set("session_id", session_id)

    # Vérifier la connexion à l'API
    api_online = await check_api_health()

    # Créer le message vide pour le streaming
    msg = cl.Message(content="")
    await msg.send()

    if api_online:
        welcome_text = """👋 **Salut ! Je suis Yann Jordan Pokam, ton assistant virtuel.**

Je suis développeur logiciel passionné, basé à Saguenay, Québec. 
Je peux te parler de :
- 🛠️ Mes **compétences techniques** (C#, Python, Django, React...)
- 📁 Mes **projets** réalisés
- 🎓 Ma **formation** et mon parcours
- 💡 Ma **vision** du développement et de l'IA

**Pose-moi une question !** Par exemple :
- "Parle-moi de toi"
- "Quels sont tes projets?"
- "Pourquoi le développement?"
"""
    else:
        welcome_text = f"""⚠️ **Impossible de se connecter à l'API**

L'API n'est pas accessible à l'adresse : `{API_BASE_URL}`

Vérifie que :
1. Ton serveur FastAPI est lancé (`uvicorn main:app --port 8001`)
2. L'URL dans `chainlit_app.py` est correcte
"""

    # Animation de frappe caractère par caractère
    for char in welcome_text:
        await msg.stream_token(char)

        # Délais variables selon le caractère
        if char in '.!?':
            await asyncio.sleep(PAUSE_PUNCTUATION)
        elif char == '\n':
            await asyncio.sleep(PAUSE_NEWLINE)
        elif char == ' ':
            await asyncio.sleep(random.uniform(MIN_DELAY, MAX_DELAY * 0.5))
        else:
            await asyncio.sleep(random.uniform(MIN_DELAY, MAX_DELAY))

    await msg.update()

    # 1. Petite pause pour le rythme
    await asyncio.sleep(0.5)

    # 2. Création du message d'attente (Auteur différent pour le style, ex: "System")
    waiting_msg = cl.Message(
        content="",
        author="System"  # Utiliser "System" le rend souvent plus discret visuellement
    )
    await waiting_msg.send()

    # 3. Animation des points flottants "..."
    # On fait une petite boucle pour simuler la réflexion/attente
    for _ in range(2):  # Répéter l'animation 2 fois
        for dots in ["🟢", "🟢🟢", "🟢🟢🟢"]:
            waiting_msg.content = f"{dots}"  # Les astérisques mettent en italique
            await waiting_msg.update()
            await asyncio.sleep(0.3)

    # 4. Affichage du message final
    waiting_msg.content = "🟢 **Je suis prêt. Pose-moi ta question !**"
    await waiting_msg.update()

    # 5. Sauvegarde de l'ID pour pouvoir supprimer ce message plus tard (Optionnel)
    # C'est utile si tu veux que ce message disparaisse quand l'utilisateur commence à écrire
    cl.user_session.set("waiting_msg_id", waiting_msg.id)


@cl.on_message
async def on_message(message: cl.Message):
    session_id = cl.user_session.get("session_id")
    question = message.content

    # 1. Nettoyage du message "Je suis prêt" si présent
    waiting_msg_id = cl.user_session.get("waiting_msg_id")
    if waiting_msg_id:
        await cl.Message(content="", id=waiting_msg_id).remove()
        cl.user_session.set("waiting_msg_id", None)

    # 2. Création du LOADER (HTML direct dans content)
    # Chainlit va interpréter les balises <div> et <style> automatiquement
    loading_html = """
    <div style="display:inline-flex;align-items:center;background:#F2F2F2;padding:10px 14px;border-radius:16px;max-width:220px;">
        <div class="chatgpt-typing">
            <span class="dot"></span><span class="dot"></span><span class="dot"></span>
        </div>
    </div>
    <style>
    .chatgpt-typing { display:flex; gap:6px; }
    .dot { width:8px; height:8px; background:#999; border-radius:50%; animation: blink 1.4s infinite ease-in-out both; }
    .dot:nth-child(2) { animation-delay: .2s; }
    .dot:nth-child(3) { animation-delay: .4s; }
    @keyframes blink { 0% { opacity:.2; transform:translateY(0); } 20% { opacity:1; transform:translateY(-2px); } 100% { opacity:.2; transform:translateY(0); } }
    </style>
    """

    # CORRECTION : On retire html=True.
    loader_msg = cl.Message(content=loading_html, author="Bot")
    await loader_msg.send()

    # 3. Préparation du message final
    final_answer_msg = cl.Message(content="", author="Bot")

    payload = {"question": question, "session_id": session_id}
    buffer = ""
    first_token_received = False

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        try:
            async with client.stream("POST", f"{API_BASE_URL}/chat/", json=payload) as response:

                if response.status_code != 200:
                    # En cas d'erreur, on met à jour le loader avec le texte d'erreur
                    loader_msg.content = f"❌ Erreur API: {response.status_code}"
                    await loader_msg.update()
                    return

                async for chunk in response.aiter_text():
                    # --- GESTION DU PREMIER TOKEN ---
                    if not first_token_received and chunk.strip():
                        first_token_received = True
                        # On supprime le message du loader
                        await loader_msg.remove()
                        # On envoie le message de réponse vide pour commencer le stream
                        await final_answer_msg.send()

                    buffer += chunk

                    # --- GESTION DE LA METADATA DE FIN ---
                    if "__METADATA__" in buffer:
                        parts = buffer.split("__METADATA__")
                        text_part = parts[0]
                        meta_part = parts[1]

                        if text_part:
                            await final_answer_msg.stream_token(text_part)

                        try:
                            if meta_part:
                                meta = json.loads(meta_part)
                                actions = []
                                if meta.get("intent") == "SQL":
                                    actions.append(cl.Action(name="sql_debug", value="show", label="Voir SQL"))
                                final_answer_msg.actions = actions
                                await final_answer_msg.stream_token(f"\n\n*[Intent: {meta.get('intent')}]*")
                        except:
                            pass
                        break

                    # --- STREAMING NORMAL ---
                    elif len(buffer) > 20:
                        to_stream = buffer[:-15]
                        buffer = buffer[-15:]
                        if to_stream:
                            for char in to_stream:
                                await final_answer_msg.stream_token(char)
                                # Petite pause optionnelle pour l'effet
                                if char in '.!?\n':
                                    await asyncio.sleep(CHUNK_PAUSE)

        except httpx.TimeoutException:
            if not first_token_received:
                loader_msg.content = "⏱️ Timeout - La requête a pris trop de temps."
                await loader_msg.update()
            else:
                await final_answer_msg.stream_token("\n[Timeout]")
            return

        except Exception as e:
            if not first_token_received:
                loader_msg.content = f"❌ Erreur : {str(e)}"
                await loader_msg.update()
            else:
                await final_answer_msg.stream_token(f"\n[Exception: {str(e)}]")
            return

    if first_token_received:
        await final_answer_msg.update()

@cl.on_chat_end
async def on_chat_end():
    """Appelé quand l'utilisateur ferme le chat"""
    session_id = cl.user_session.get("session_id")

    # Optionnel: Nettoyer l'historique côté API
    async with httpx.AsyncClient() as client:
        try:
            await client.delete(f"{API_BASE_URL}/history/{session_id}")
        except:
            pass  # Ignorer les erreurs de cleanup
