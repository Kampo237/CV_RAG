"""
Module de Génération - Chaîne finale de génération de réponses avec Claude

Composants:
- rephrase_question: Reformulation contextuelle (gestion historique)
- get_generation_chain: Génération de la réponse finale
"""
import os
from typing import List, Optional
from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from langchain_core.messages import HumanMessage, AIMessage, AIMessageChunk
from fastapi import HTTPException
from dotenv import load_dotenv
import unicodedata
from typing import AsyncGenerator
import re, time, asyncio

load_dotenv()

MAX_RETRIES = 3
HEARTBEAT_INTERVAL = 10


def get_llm(temperature: float = 0) -> ChatAnthropic:
    """Retourne une instance du LLM Claude configurée"""
    return ChatAnthropic(
        model_name="claude-haiku-4-5-20251001",
        temperature=temperature,
        api_key=os.getenv("ANTHROPIC_API_KEY")
    )


# =============================================================================
# REFORMULATION DE QUESTION (Contextualisation)
# =============================================================================

def normalize_text(text: str) -> str:
    if not text:
        return ""

    # Normalise les caractères (accents, lettres étrangères, etc.)
    text = unicodedata.normalize("NFKC", text)

    # Supprime caractères non imprimables
    text = "".join(ch for ch in text if ch.isprintable())

    return text

def clean_and_fix(text: str) -> str:
    if not text:
        return ""

    # 1. Normalisation Unicode
    text = normalize_text(text)

    # 2. Trim des espaces
    text = text.strip()

    # 3. Collapse des espaces multiples
    text = " ".join(text.split())

    # 4. Mini dictionnaire de corrections
    corrections = {
        "koi": "quoi",
        "pk": "pourquoi",
        "c koi": "c’est quoi",
        "stp": "s’il te plaît",
        "svp": "s’il vous plaît",
        "ya": "il y a",
        "ya pas": "il n’y a pas",
    }

    for wrong, right in corrections.items():
        text = re.sub(rf"\b{wrong}\b", right, text, flags=re.IGNORECASE)

    return text

def rephrase_question(question: str, history: List[dict]) -> str:
    """
    Reformule une question en incluant le contexte de l'historique
    
    Permet de gérer les questions de suivi comme:
    - "Et quelles technologies y as-tu utilisées?" → "Quelles technologies as-tu utilisées dans [projet mentionné]?"
    - "C'est intéressant, dis-m'en plus" → "Donne plus de détails sur [sujet précédent]"
    
    Args:
        question: Question actuelle de l'utilisateur
        history: Liste des échanges précédents [{"role": "user"|"assistant", "content": "..."}]
    
    Returns:
        Question reformulée avec contexte complet
    """
    # Si pas d'historique, retourner la question telle quelle

    clean_question = clean_and_fix(question)
    question = clean_question

    if not history:
        return question
    
    llm = get_llm(temperature=0)
    
    # Formater l'historique pour le prompt
    history_text = "\n".join([
        f"{'Utilisateur' if msg['role'] == 'user' else 'Assistant'}: {msg['content']}"
        for msg in history[-6:]  # Limiter aux 6 derniers messages (3 échanges)
    ])
    
    rephrase_prompt = ChatPromptTemplate.from_messages([
        ("system", """Tu es un assistant qui reformule les questions pour qu'elles soient autonomes et complètes, tout en corrigeant les fautes de français 
        s'il y en a.

Étant donné l'historique de conversation et la nouvelle question de l'utilisateur, 
reformule la question pour qu'elle soit compréhensible SANS avoir besoin de l'historique.

Règles:
- Si la question fait référence à un élément précédent ("ça", "cela", "y", "il"), remplace par le terme explicite
- Si la question est déjà autonome et claire, retourne-la telle quelle en corrigeant les fautes de français s'il y a lieu
- Ne change pas le sens de la question
- Garde la reformulation concise

Réponds UNIQUEMENT avec la question reformulée, sans explication."""),
        ("human", """Historique:
{history}

Nouvelle question: {question}

Question reformulée:""")
    ])
    
    chain = rephrase_prompt | llm | StrOutputParser()
    
    try:
        rephrased = chain.invoke({
            "history": history_text,
            "question": question
        })
        return rephrased.strip()
    except Exception as e:
        print(f"Erreur reformulation: {e}")
        return question  # Fallback: question originale

async def rephrase_question_async(question: str, history: List[dict]) -> str:
    """Version asynchrone de rephrase_question"""
    if not history:
        return question
    
    llm = get_llm(temperature=0)
    
    history_text = "\n".join([
        f"{'Utilisateur' if msg['role'] == 'user' else 'Assistant'}: {msg['content']}"
        for msg in history[-6:]
    ])
    
    rephrase_prompt = ChatPromptTemplate.from_messages([
        ("system", """Tu es un assistant qui reformule les questions pour qu'elles soient autonomes et complètes.
Reformule la question pour qu'elle soit compréhensible sans l'historique en corrigeant les fautes s'il y a lieu.
Réponds UNIQUEMENT avec la question reformulée."""),
        ("human", """Historique:
{history}

Nouvelle question: {question}

Question reformulée:""")
    ])
    
    chain = rephrase_prompt | llm | StrOutputParser()
    
    try:
        rephrased = await chain.ainvoke({
            "history": history_text,
            "question": question
        })
        return rephrased.strip()
    except Exception:
        return question

# =============================================================================
# CHAÎNE DE GÉNÉRATION FINALE
# =============================================================================

def get_generation_chain():
    """
    Crée la chaîne de génération de réponse finale
    
    Attend en entrée:
    - context: Texte contextuel (résultat SQL ou documents vectoriels)
    - question: Question reformulée
    - history: Historique formaté (optionnel)
    
    Returns:
        Chaîne LangChain exécutable
    """
    llm = get_llm(temperature=0.2)
    
    generation_prompt = ChatPromptTemplate.from_messages([
        ("system", """Tu es l'assistant virtuel du portfolio de Yann Willy Jordan Pokam Teguia, 
un jeune diplômé en Techniques de l'informatique au Cégep de Chicoutimi.

Ton rôle est de répondre aux questions des recruteurs et visiteurs de manière:
- Professionnelle mais accessible
- Précise et basée sur les informations fournies
- Engageante et représentative de la personnalité de Yann

RÈGLES IMPORTANTES:
1. Base tes réponses UNIQUEMENT sur le contexte fourni
2. Si l'information n'est pas dans le contexte, dis-le poliment
3. Ne jamais inventer d'informations sur le parcours, les projets ou les compétences
4. Reste focalisé sur le profil professionnel (pas de sujets personnels inappropriés)
5. Utilise un ton naturel et conversationnel
6. Si pertinent, mentionne des exemples concrets du contexte

Format de réponse:
- Réponses concises mais toujours complètes
- Utilise des paragraphes courts
- Évite les listes à puces sauf si vraiment nécessaire"""),
        
        ("human", """Contexte disponible:
{context}

Historique de conversation:
{history}

Question: {question}

Réponse:""")
    ])
    
    return generation_prompt | llm | StrOutputParser()

async def generate_response(question: str,context: str,history: Optional[List[dict]] = None) -> str:
    """
    Génère une réponse complète
    
    Args:
        question: Question (déjà reformulée de préférence)
        context: Contexte textuel pour la réponse
        history: Historique optionnel
    
    Returns:
        Réponse générée par Claude
    """
    chain = get_generation_chain()
    
    # Formater l'historique
    history_text = ""
    if history:
        history_text = "\n".join([
            f"{'Q' if msg['role'] == 'user' else 'R'}: {msg['content']}"
            for msg in history[-4:]  # Derniers 2 échanges
        ])

    payload = {
        "context": context,
        "question": question,
        "history": history_text or "Aucun historique."
    }

    retry = 0

    while retry < MAX_RETRIES:
        try:
            async for chunk in chain.astream(payload):
                # On extrait juste le texte
                content = ""
                if isinstance(chunk, str):
                    content = chunk
                elif isinstance(chunk, AIMessageChunk):
                    content = chunk.content

                if content:
                    yield content

            return

        except Exception as e:
            retry += 1
            if retry >= MAX_RETRIES:
                # On yield l'erreur pour qu'elle s'affiche dans le chat
                yield f"\n[Erreur génération: {str(e)}]"
                return
            await asyncio.sleep(retry)


# =============================================================================
# RÉPONSES PRÉDÉFINIES
# =============================================================================

OFF_TOPIC_RESPONSES = [
    "Haha, bonne question, mais là tu me sors un peu de ma zone ! "
    "Je suis programmé pour parler de mon parcours, mes projets et mes compétences. "
    "Qu'est-ce qui t'intéresse côté tech ou expérience?",

    "Hé, c'est tentant de partir sur ce sujet, mais je préfère rester focus sur ce que je maîtrise : "
    "mon CV, mes projets et ma vision du développement. On y revient?",

    "Je vois où tu veux en venir, mais disons que ce n'est pas mon domaine d'expertise ! "
    "Par contre, si tu veux savoir comment je structure mes APIs ou mes projets en équipe, là je suis ton gars.",

    "Oh là, on s'éloigne un peu du sujet ! Mais je comprends la curiosité. "
    "Recentrons-nous : qu'est-ce que tu aimerais savoir sur mon parcours ou mes compétences techniques?",

    "Intéressant comme question... mais pas vraiment dans mes cordes ici ! "
    "Je suis là pour te parler de développement, de projets concrets et de ma vision du métier. On y va?",

    "Haha, je garde ça pour une vraie discussion autour d'un café ! "
    "Ici, je me concentre sur mon profil pro. Une question sur mes projets ou mes technos préférées?",

    "C'est le genre de question que j'adore... mais en dehors de ce chatbot ! "
    "Pour l'instant, parlons de ce qui pourrait t'intéresser dans mon parcours. Qu'est-ce qui t'amène?",

    "Je pourrais improviser une réponse, mais ce serait tricher ! "
    "Mon expertise ici, c'est de te présenter mon profil. Alors, curieux de savoir quelque chose sur mes projets?"
]

NO_CONTEXT_RESPONSE = (
    "Hmm, je n'ai pas d'information précise là-dessus dans ma base de connaissances. "
    "Mais si tu reformules ou me poses une question connexe, je pourrai sûrement t'aider ! "
    "Sinon, n'hésite pas à contacter Yann directement pour approfondir."
)

def get_off_topic_response() -> str:
    """Retourne une réponse aléatoire pour les questions hors-sujet"""
    import random
    return random.choice(OFF_TOPIC_RESPONSES)

