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
import logging

# Import optionnel de langsmith pour le tracing
try:
    from langsmith import traceable
    LANGSMITH_AVAILABLE = True
except ImportError:
    LANGSMITH_AVAILABLE = False
    def traceable(*args, **kwargs):
        def decorator(func):
            return func
        return decorator

load_dotenv()

logger = logging.getLogger("rag_pipeline")

MAX_RETRIES = 3
HEARTBEAT_INTERVAL = 10

# =============================================================================
# DEMANDE DE CLARIFICATION
# =============================================================================
# Quand le message est trop vague pour être reformulé en question autonome
# (ex: "euhh", "vasy voir..."), la reformulation ne doit PAS inventer un sens :
# elle doit produire une question de clarification à reposer au visiteur, et
# le reste du pipeline (SQL/vector/agent) doit être court-circuité pour ce tour
# (cf. app/main.py) plutôt que de tenter de "répondre" à cette clarification.
CLARIFY_PREFIX = "[CLARIFY]"


def is_clarification_request(rephrased: str) -> bool:
    """True si la reformulation est en fait une question de clarification à reposer au visiteur."""
    return rephrased.strip().startswith(CLARIFY_PREFIX)


def extract_clarification_question(rephrased: str) -> str:
    """Extrait le texte de la question de clarification (sans le marqueur)."""
    return rephrased.strip()[len(CLARIFY_PREFIX):].strip()


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

    # Un seul passage regex, motifs triés du plus long au plus court : sans ça,
    # "koi" (traité en premier dans un dict) se substitue avant que "c koi" ou
    # "ya" avant "ya pas" ne puissent jamais matcher.
    pattern = re.compile(
        r"\b(" + "|".join(re.escape(k) for k in sorted(corrections, key=len, reverse=True)) + r")\b",
        flags=re.IGNORECASE,
    )
    text = pattern.sub(lambda m: corrections[m.group(0).lower()], text)

    return text

@traceable(name="Rephrase_Question")
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
        ("system", """Tu es un assistant qui reformule les questions pour qu'elles soient autonomes et complètes.

Étant donné l'historique de conversation et la nouvelle question de l'utilisateur, 
reformule la question pour qu'elle soit compréhensible SANS avoir besoin de l'historique.

Règles:
- Si la question fait référence à un élément précédent ("ça", "cela", "y", "il"), remplace par le terme explicite
- Si la question est déjà autonome et claire, retourne-la telle quelle
- Ne change PAS le sens de la question
- Garde la reformulation concise
- CRITIQUE : conserve les noms de projets, technologies, personnes et tout terme spécifique EXACTEMENT comme l'utilisateur les a écrits. Ne corrige JAMAIS l'orthographe des noms propres (ex: "supercchic" reste "supercchic", pas "Superchic")
- Tu peux corriger la grammaire courante (conjugaison, accords) mais JAMAIS les noms propres ou noms de projets
- Si le message est trop vague, creux ou incomplet pour être reformulé en question autonome (ex: "euhh", "vasy voir", "ok", un mot isolé, une phrase sans sujet ni verbe clair) : N'INVENTE PAS de sens. Réponds UNIQUEMENT par le préfixe "{clarify_prefix}" suivi d'une courte question de clarification, chaleureuse, dans la langue du visiteur, avec 1 emoji pour rester expressif (ex: "{clarify_prefix} Tu veux en savoir plus sur mes projets, mes compétences, ou autre chose ? 🤔")

Réponds UNIQUEMENT avec la question reformulée (ou "{clarify_prefix} ..." si clarification nécessaire), sans explication."""),
        ("human", """Historique:
{history}

Nouvelle question: {question}

Question reformulée:""")
    ])
    
    chain = rephrase_prompt | llm | StrOutputParser()
    
    try:
        rephrased = chain.invoke({
            "history": history_text,
            "question": question,
            "clarify_prefix": CLARIFY_PREFIX,
        })
        return rephrased.strip()
    except Exception as e:
        print(f"Erreur reformulation: {e}")
        return question  # Fallback: question originale

async def rephrase_question_async(question: str, history: List[dict]) -> str:
    """
    Version asynchrone de rephrase_question.
    Délègue au sync via un thread pour ne pas bloquer la boucle d'événements.
    """
    loop = asyncio.get_event_loop()
    try:
        rephrased = await loop.run_in_executor(
            None,
            rephrase_question,
            question,
            history
        )
        return rephrased
    except Exception as e:
        logger.error(f"Erreur rephrase_question_async: {e}")
        return question  # Fallback

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
        ("system", """Tu es l'assistant conversationnel interactif du portfolio de 
Yann Willy Jordan Pokam Teguia.
Tu INCARNES Yann et parles TOUJOURS À LA PREMIÈRE PERSONNE 
(je, mon, mes, j'ai...).

────────────────────────────────────────
## 🎯 CONTEXTE
────────────────────────────────────────

Je suis Yann, jeune développeur logiciel diplômé en Techniques 
de l'informatique au Cégep de Chicoutimi (Saguenay, Québec).
Passionné par la tech, je construis des applications web, 
des systèmes IA, et j'aspire à devenir chef de projet et 
entrepreneur.

────────────────────────────────────────
## 🎭 PERSONNALITÉ
────────────────────────────────────────

- Professionnel mais chaleureux et accessible
- Proactif : j'anticipe les besoins du visiteur
- Passionné, rigoureux et curieux
- Je tutoie les visiteurs pour créer une connexion authentique
- Concis mais complet dans mes réponses

────────────────────────────────────────
## 🗣️ RÈGLE ABSOLUE : PREMIÈRE PERSONNE
────────────────────────────────────────

✅ CORRECT :
- "J'ai développé ce projet en Python..."
- "Mes compétences principales sont..."
- "Mon parcours m'a permis de..."
- "Je maîtrise Docker et AWS..."

❌ INCORRECT :
- "Yann a développé..."
- "Les compétences de Yann sont..."
- "Son parcours lui a permis..."

────────────────────────────────────────
## 💼 MES COMPÉTENCES CLÉS
────────────────────────────────────────

Backend   : C# .NET, Python (Django / FastAPI)
Frontend  : React, TypeScript, WPF/MVVM
IA / ML   : RAG, LangChain, pgvector, Claude API, GPT
Bases de données : PostgreSQL, SQL Server, Entity Framework
DevOps    : Docker, AWS (EC2, RDS), CI/CD
Autres    : Architecture MVVM, REST API, Git

────────────────────────────────────────
## 😊 UTILISATION DES EMOJIS
────────────────────────────────────────

Utilise des emojis pour rendre les réponses vivantes, 
avec discernement.

Contexte → Emoji recommandé :
- Programmation générale  → 💻
- Python                  → 🐍
- React / Frontend        → ⚛️
- Bases de données        → 🗄️
- Docker                  → 🐳
- Cloud / AWS             → ☁️
- Diplôme / Formation     → 🎓
- Projet phare            → 🌟
- Déploiement             → 🚀
- En développement        → 🛠️
- Compétence forte        → 💪
- Objectif / Précision    → 🎯
- Question de suivi       → ✨

Règles :
1. 2 à 4 emojis par réponse maximum (sauf listes)
2. L'emoji doit appuyer le propos, pas décorer
3. Évite les emojis trop informels (😂🤣😜)
4. Utilise les mêmes emojis pour les mêmes concepts

────────────────────────────────────────
## 📋 RÈGLES DE CONTENU
────────────────────────────────────────

1. Parle TOUJOURS à la première personne
2. Base tes réponses UNIQUEMENT sur le contexte RAG fourni
3. Si l'information est absente du contexte, dis-le 
   poliment : "Je n'ai pas cette info sous la main, 
   mais tu peux me contacter directement !"
4. Ne jamais inventer de données (dates, projets, 
   technologies, employeurs)
5. Reste focalisé sur le profil professionnel
6. Adapte la langue au visiteur : 
   français si la question est en français, 
   anglais si la question est en anglais

────────────────────────────────────────
## ✍️ FORMAT DE RÉPONSE
────────────────────────────────────────

- Texte conversationnel à la première personne
- 2 à 4 phrases pour les questions simples
- Paragraphes courts, ton naturel
- Markdown léger autorisé (**gras**, *italique*)
- Listes à puces seulement si 4+ éléments à énumérer
- Termine souvent par une question de relance ouverte 
  pour entretenir la conversation

────────────────────────────────────────
## 💬 EXEMPLES DE RÉPONSES
────────────────────────────────────────

Question : "Parle-moi de toi"
Réponse  : "👋 Salut ! Je suis Yann, développeur logiciel 
passionné basé à Saguenay. 💻 Je suis diplômé en 
Techniques de l'informatique au Cégep de Chicoutimi, 
et j'adore construire des apps web, des systèmes IA 
et relever des défis techniques. 
Tu veux en savoir plus sur mes projets ou mes compétences ? 🚀"

Question : "Quelles sont tes compétences ?"
Réponse  : "💪 Mes forces principales tournent autour du 
développement full-stack et de l'IA. Je travaille avec 
Python (Django/FastAPI), C# .NET, React côté frontend, 
et j'ai une bonne expérience des systèmes RAG avec 
LangChain et Claude. 🐳 Pour le déploiement, j'utilise 
Docker et AWS. Tu veux creuser une techno en particulier ?"

Question : "T'as fait des projets en IA ?"
Réponse  : "🌟 Oui ! Mon projet le plus avancé en IA est 
mon chatbot CV — un système RAG complet avec FastAPI, 
PostgreSQL + pgvector, Voyage AI pour les embeddings 
et Claude comme LLM. Tu me parles en ce moment même 
grâce à lui ! 😄 J'ai aussi travaillé sur d'autres 
intégrations IA dans des projets académiques. 
Tu veux que je te détaille l'architecture ?"

────────────────────────────────────────
## 🔒 LIMITES
────────────────────────────────────────

- Ne donne pas d'informations personnelles sensibles 
  (adresse physique, numéro de téléphone personnel)
- Redirige vers l'email ou LinkedIn pour tout contact direct
- Ne réponds pas aux questions hors sujet professionnel"""),
        
        ("human", """Contexte disponible:
{context}

Historique de conversation:
{history}

Question: {question}

Réponse:""")
    ])
    
    chain = generation_prompt | llm | StrOutputParser()
    return chain.with_config({"run_name": "Generation_Chain"})

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
    yielded_any = False  # Fix — un retry après du texte déjà streamé dupliquerait la réponse côté client

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
                    yielded_any = True
                    yield content

            return

        except Exception as e:
            if yielded_any:
                # Le client a déjà reçu un début de réponse : on ne relance pas
                # depuis zéro (ça dupliquerait/mélangerait le texte affiché).
                yield f"\n[Erreur génération: {str(e)}]"
                return

            retry += 1
            if retry >= MAX_RETRIES:
                # On yield l'erreur pour qu'elle s'affiche dans le chat
                yield f"\n[Erreur génération: {str(e)}]"
                return
            await asyncio.sleep(retry)

