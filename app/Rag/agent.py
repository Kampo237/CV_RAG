"""
RAG Agent — Pipeline agentique avec LangGraph ReAct

Utilisé pour les questions que le chemin rapide (fast_path.py) ne couvre pas :
questions qualitatives, mélanges fait + explication, message à Jordan.

Architecture :
  question → (reformulation si nécessaire) → Agent ReAct [LLM + tools] → réponse

Outils (cf. BACKEND_NEON_SOURCE_DE_VERITE.md) :
  - get_projects / get_profile / get_experiences / get_education /
    get_skills / get_testimonials : lignes des tables canoniques Neon, via des
    requêtes SQL écrites à la main (plus de SELECT généré par un LLM) ;
  - search_knowledge_base : recherche vectorielle (cache dérivé des tables
    canoniques), filtrable par catégorie avant le tri par similarité ;
  - set_site_theme / navigate_site / open_project : actions sur le site ; le
    code en tire la ligne [[guide]] (plus d'action annoncée mais non faite) ;
  - prepare_contact_message / send_contact_message : message à Jordan, étapes
    imposées par le code (contact.py), livraison via le serveur MCP SMS.
"""

import os
import logging
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import AIMessageChunk, SystemMessage
from langgraph.prebuilt import create_react_agent

from app.Rag import canonical
from app.Rag.retrieval import retrieve_and_rerank, format_context
from app.Rag.vector_store import get_vector_store_service
from app.Rag.generation import rephrase_question_async
from app.Rag.fast_path import last_answer_asked

from app.Rag import contact as contact_service
from app.Rag.guide import validate_actions, THEME_MODES

load_dotenv()
logger = logging.getLogger("rag_pipeline")


# =============================================================================
# SINGLETONS
# =============================================================================

_llm_agent: Optional[ChatAnthropic] = None

# claude-sonnet-5 réfléchit par défaut (thinking adaptatif) à effort "high" :
# c'est la plus grosse part de la latence de chaque tour de l'agent. Pour un
# chatbot de portfolio, "low" suffit (moins de réflexion, moins d'appels
# d'outils, pas de préambule). Le SDK installé ne connaît pas encore
# `output_config` comme argument nommé → on le passe via extra_body.
AGENT_EFFORT = os.getenv("AGENT_EFFORT", "low")


def _get_agent_llm() -> ChatAnthropic:
    """LLM de l'agent — Sonnet pour le raisonnement et le tool calling."""
    global _llm_agent
    if _llm_agent is None:
        _llm_agent = ChatAnthropic(
            model_name="claude-sonnet-5",
            # `temperature` est refusé par ce modèle (400 invalid_request_error) — ne pas le passer.
            api_key=os.getenv("ANTHROPIC_API_KEY"),
            model_kwargs={"extra_body": {"output_config": {"effort": AGENT_EFFORT}}},
        )
    return _llm_agent


# Catégories du cache `datas` / embeddings (cf. app/rebuild_knowledge_cache.py)
KNOWLEDGE_CATEGORIES = ("identite", "experience", "formation", "competence", "projet", "contact")

NO_INFO = "Aucune ligne en base. Réponds : « Je n'ai pas cette information. »"


# =============================================================================
# OUTILS (TOOLS) — Ce que l'agent peut appeler
# =============================================================================

async def _canonical_tool(kind: str) -> str:
    try:
        rows = await canonical.fetch(kind)
    except Exception as e:
        logger.error(f"[tool {kind}] Erreur: {e}")
        return f"Erreur de lecture de la base: {e}"
    return canonical.format_rows(rows) if rows else NO_INFO


@tool
async def get_projects() -> str:
    """Liste des projets ACTIFS du portfolio (titre, slug, descriptions, technologies, dates, liens).

    Source de vérité pour tout projet : n'en cite aucun qui n'est pas dans ce résultat.
    Le slug retourné est celui à utiliser dans une action open_project.
    """
    return await _canonical_tool("projects")


@tool
async def get_profile() -> str:
    """Identité et coordonnées publiques : nom, bio, email, liens (GitHub, LinkedIn), disponibilité, cv_pdf.

    Seule source pour le contact et le CV PDF.
    """
    return await _canonical_tool("profile")


@tool
async def get_experiences() -> str:
    """Expériences professionnelles (emplois, stages, entreprises, dates), avec leur statut
    calculé : poste principal actuel, emploi secondaire (temps partiel), sur appel, ou terminé."""
    try:
        rows = await canonical.fetch("experiences")
    except Exception as e:
        logger.error(f"[tool experiences] Erreur: {e}")
        return f"Erreur de lecture de la base: {e}"
    return canonical.format_rows(canonical.annotate_experiences(rows)) if rows else NO_INFO


@tool
async def get_education() -> str:
    """Formation (diplômes, établissements, dates), avec leur statut calculé
    (terminé — diplôme obtenu, terminé sans diplôme, ou en cours)."""
    try:
        rows = await canonical.fetch("education")
    except Exception as e:
        logger.error(f"[tool education] Erreur: {e}")
        return f"Erreur de lecture de la base: {e}"
    return canonical.format_rows(canonical.annotate_formations(rows)) if rows else NO_INFO


@tool
async def get_skills() -> str:
    """Compétences techniques (langages, frameworks, outils, niveaux).

    Utilise-le pour vérifier si une technologie est connue (« Tu connais Docker ? »).
    """
    return await _canonical_tool("skills")


@tool
async def get_testimonials() -> str:
    """Témoignages approuvés laissés par des personnes ayant travaillé avec Jordan."""
    return await _canonical_tool("testimonials")


@tool
async def search_knowledge_base(query: str, category: Optional[str] = None) -> str:
    """Recherche sémantique pour les questions qualitatives (motivations, façon de travailler,
    récit d'une expérience ou d'un projet).

    Args:
        query: La question ou les mots-clés à rechercher
        category: filtre optionnel appliqué AVANT le tri par similarité, parmi
            identite, experience, formation, competence, projet, contact
    """
    if category and category not in KNOWLEDGE_CATEGORIES:
        category = None
    try:
        docs = await retrieve_and_rerank(
            query=query,
            vector_store_service=get_vector_store_service(),
            initial_k=8,
            final_k=3,
            category=category,
        )
        if not docs:
            return "Aucun document pertinent trouvé dans la base de connaissances."
        return format_context(docs)
    except Exception as e:
        logger.error(f"[search_knowledge_base] Erreur: {e}")
        return f"Erreur lors de la recherche: {e}"


# =============================================================================
# SYSTEM PROMPT DE L'AGENT
# =============================================================================

AGENT_SYSTEM_PROMPT = """Tu es l'assistant conversationnel du portfolio de Yann Willy Jordan Pokam Teguia,
technicien en informatique. Son prénom d'usage est JORDAN (jamais « Yann » pour te présenter).
Tu INCARNES Jordan et parles à la PREMIÈRE PERSONNE (je, mon, mes).

────────────────────────────────────────
## RÔLE ET POSTURE
────────────────────────────────────────

Ton rôle est d'aider les visiteurs à découvrir le profil de Jordan en
répondant à leurs questions avec authenticité. Tu es chaleureux, accessible,
et professionnel.

RÈGLE D'HUMILITÉ ABSOLUE :
- Tu parles de tes compétences avec honnêteté, sans exagération ni fausse modestie.
- Tu ne prétends JAMAIS maîtriser parfaitement quelque chose. Utilise des formulations
  comme : "j'ai une bonne expérience en...", "j'ai travaillé avec...",
  "je suis à l'aise avec...", "j'ai exploré..."
- Tu NE DIS JAMAIS : "je suis expert en...", "je maîtrise..." (même "je maîtrise bien"),
  "je suis le meilleur en..." — même si les données le suggèrent.
- Quand tu ne sais pas, tu dis simplement : "Je n'ai pas cette information."
- Pour les questions sensibles ou très personnelles, préfère TOUJOURS :
  "Je t'invite à me contacter directement pour en parler" plutôt que
  de spéculer ou d'inventer.
- Tu es un jeune développeur en début de carrière — ton ton doit refléter
  ça : enthousiaste, curieux, travailleur, mais pas prétentieux.

────────────────────────────────────────
## OUTILS DE RECHERCHE
────────────────────────────────────────

Sources de vérité (lignes de la base, lues pendant la requête) :
- get_projects : projets actifs (seuls projets que tu as le droit de citer)
- get_profile : identité, contact, liens, disponibilité, CV PDF (colonne cv_pdf)
- get_experiences, get_education, get_skills : expériences, formation, compétences
- get_testimonials : témoignages approuvés

Complément pour le qualitatif (motivations, façon de travailler, récit) :
- search_knowledge_base(query, category) — filtre category si la question vise
  un seul domaine (identite, experience, formation, competence, projet, contact)

Règles de source (STRICTES) :
1. Chaque phrase factuelle vient d'un résultat d'outil de CETTE requête.
   Jamais de ta mémoire, jamais d'une FAQ.
2. Les lignes des outils get_* priment sur search_knowledge_base : en cas de
   contradiction, la ligne get_* fait foi. Un projet absent de get_projects
   n'est pas cité, même s'il apparaît dans la base de connaissances.
3. Si les outils ne ramènent rien : « Je n'ai pas cette information. »
   Pas de projet de remplacement, pas de promesse d'envoi.
4. CV PDF : seulement la valeur de cv_pdf. Vide → tu n'as pas l'information
   (ne dis pas qu'il n'existe pas, ne propose pas de l'envoyer par texto).
5. N'écris AUCUN texte avant d'appeler un outil : ta réponse est diffusée en
   direct au visiteur.
6. Poste actuel : seulement l'expérience dont le statut commence par « ⭐ poste
   principal actuel ». Les emplois secondaires et sur appel ne sont cités que si le visiteur
   demande tous mes emplois, avec leur statut exact (un poste sur appel n'est ni un
   emploi régulier ni un temps partiel).

────────────────────────────────────────
## RÈGLES DE RÉPONSE
────────────────────────────────────────

- Parle TOUJOURS à la première personne (je, mon, mes)
- Utilise 1-2 emojis par réponse, pas plus. Discrets et pertinents.
- Sois concis : 2-4 phrases pour les questions simples.
- Si aucune information n'est trouvée : « Je n'ai pas cette information. »
- Ne JAMAIS inventer de données (dates, projets, technologies, niveaux).
- Pour les questions hors-sujet, redirige poliment vers le profil.
- Quand un visiteur exprime de l'intérêt pour le profil ou demande comment
  me contacter, mentionne subtilement : "Tu peux aussi me laisser un message
  via ce chat et je peux te le transmettre directement par texto si tu veux."
  Ne le mentionne qu'une seule fois par conversation, et seulement si c'est naturel.
- Adapte la langue au visiteur (français/anglais).
- Ne termine PAS systématiquement par une question : le plus souvent, conclus simplement ou
  laisse une ouverture sans point d'interrogation. Une relance reste possible de temps en temps.
- Si le message du visiteur mêle une demande (navigation, thème) et un commentaire ou une
  question, fais l'action ET réponds au reste du message.

────────────────────────────────────────
## EXEMPLES DE RÉPONSES HUMBLES
────────────────────────────────────────

(Les crochets sont à remplacer par des faits issus des outils.)

❌ MAUVAIS : "Je maîtrise parfaitement [techno A], [techno B] et [techno C] ! 💪🚀"
✅ BON : "J'ai une bonne base en [techno A], et j'ai beaucoup exploré [techno B]."

❌ MAUVAIS : "[Projet] est le projet le plus avancé que tu verras !"
✅ BON : "[Projet] est le projet dont je suis le plus fier — c'est celui qui
   m'a le plus appris techniquement."

❌ MAUVAIS : "Je suis un expert en [domaine]."
✅ BON : "[Domaine] me passionne et je continue d'y apprendre."
"""

# Outils d'action et de contact : décrits au modèle, mais leurs règles (pages
# et ancres valides, une seule visite, étapes du message à Jordan) sont
# appliquées par le code, pas par le prompt.
ACTIONS_PROMPT = """────────────────────────────────────────
## ACTIONS SUR LE SITE (outils)
────────────────────────────────────────

Tu agis sur le site avec des outils ; le site exécute l'action à la fin de ta réponse.
- set_site_theme(mode) : thème "light" (clair) ou "dark" (sombre). Le contexte du
  message indique le thème actuel : s'il est déjà celui demandé, dis-le sans appeler l'outil.
- navigate_site(path, target) : ouvre une page et surligne éventuellement une section.
- open_project(slug, section) : ouvre la fiche d'un projet, et éventuellement une section.

Règles :
- Ne dis JAMAIS avoir changé le thème, ouvert une page ou surligné une zone sans avoir
  appelé l'outil, et ne dis jamais que tu ne peux pas le faire.
- Une seule visite par réponse (navigate_site OU open_project).
- Pas d'action si la réponse suffit, si l'endroit n'existe pas ou si la demande est ambiguë.
- N'écris jamais de JSON ni de ligne technique dans ta réponse.

Pages : /  /about  /projects  /cv  /testimonials
Sections : accueil → home-hero, home-about, home-projects, home-approach, home-stats,
home-contact ; /about → about-intro, about-skills, about-values, about-interests ;
/projects → projects-grid ; /cv → cv-download, cv-experience, cv-education, cv-languages,
cv-distinctions, cv-certifications ; /testimonials → testimonials-list ; partout → site-nav.
Sections d'une fiche (open_project) : overview, problem, approach, features, results, gallery.

Projets actifs (titre — slug) :
{projects}

────────────────────────────────────────
## MESSAGE À JORDAN (outils)
────────────────────────────────────────

Quand le visiteur veut laisser un message, être recontacté ou rappelé :
1. Il faut son nom, un moyen de le recontacter (courriel OU téléphone, au choix du
   visiteur) et son message. Demande seulement ce qui manque, en une fois.
2. Appelle prepare_contact_message, puis montre le récapitulatif renvoyé et demande
   une confirmation (oui / non).
3. Au message suivant : s'il confirme, appelle DIRECTEMENT send_contact_message (sans
   rappeler prepare_contact_message) ; s'il refuse ou hésite, n'envoie rien.
4. N'annonce un envoi que si l'outil répond « ENVOYÉ ». Sur « REFUS », « INCOMPLET » ou
   « ÉCHEC », dis simplement ce qu'il en est.
- Le message va toujours à Jordan ; tu ne peux ni appeler ni écrire au visiteur toi-même :
  c'est Jordan qui le recontactera.
- Ne propose jamais d'envoyer un document (CV, etc.) par texto.
"""


# =============================================================================
# OUTILS COMMUNS
# =============================================================================

LOCAL_TOOLS = [get_projects, get_profile, get_experiences, get_education,
               get_skills, get_testimonials, search_knowledge_base]


def _extract_text(content) -> str:
    """
    Extrait le texte d'un AIMessage.content.

    Selon le modèle, .content peut être une simple str OU une liste de blocs
    (ex: claude-sonnet-5 renvoie [{"type": "thinking", ...}, {"type": "text",
    "text": "..."}] avec l'extended thinking) — sans cette extraction, un
    `list` remonte tel quel jusqu'au streaming de main.py qui appelle
    .split(" ") dessus et plante ('list' object has no attribute 'split').
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return str(content) if content else ""


# =============================================================================
# OUTILS LIÉS À LA REQUÊTE (actions sur le site, message à Jordan)
# =============================================================================

@dataclass
class TurnContext:
    """Ce que les outils d'une requête partagent : session, message brut, contexte du site."""
    session_id: str
    user_message: str
    site: dict = field(default_factory=dict)      # {"theme": "light"|"dark", "path": "/…"}
    slugs: set = field(default_factory=set)
    actions: list = field(default_factory=list)   # actions validées → ligne [[guide]]


def _site_note(site: dict) -> str:
    parts = []
    if site.get("path"):
        parts.append(f"page actuelle {site['path']}")
    if site.get("theme") in THEME_MODES:
        parts.append(f"thème actuel {'sombre' if site['theme'] == 'dark' else 'clair'}")
    return f"\n\n(Contexte du site : {', '.join(parts)}.)" if parts else ""


def _request_tools(ctx: TurnContext) -> list:
    def _add(new_actions: list[dict]) -> str:
        candidate = ctx.actions + new_actions
        valid = validate_actions(candidate, ctx.slugs)
        if len(valid) < len(candidate):
            return ("REFUS : action invalide (une seule visite par réponse ; pages, sections et slugs "
                    "de la liste uniquement). Rien n'a été changé.")
        ctx.actions[:] = valid
        return "OK : le site exécutera l'action à la fin de ta réponse."

    @tool
    async def set_site_theme(mode: str) -> str:
        """Passe le site en mode clair ou sombre.

        Args:
            mode: "light" (clair) ou "dark" (sombre)
        """
        mode = {"clair": "light", "sombre": "dark"}.get((mode or "").strip().lower(), (mode or "").strip().lower())
        if mode not in THEME_MODES:
            return "REFUS : mode attendu « light » ou « dark »."
        if ctx.site.get("theme") == mode:
            return f"Le site est déjà en mode {'sombre' if mode == 'dark' else 'clair'} : dis-le simplement."
        return _add([{"op": "set_theme", "mode": mode}])

    @tool
    async def navigate_site(path: str, target: Optional[str] = None) -> str:
        """Ouvre une page du site pour le visiteur et surligne éventuellement une section.

        Args:
            path: "/", "/about", "/projects", "/cv" ou "/testimonials"
            target: section à surligner (ex. "about-skills", "cv-languages", "testimonials-list")
        """
        actions = [{"op": "navigate", "path": (path or "").strip()}]
        if target:
            actions.append({"op": "focus", "target": target.strip()})
        return _add(actions)

    @tool
    async def open_project(slug: str, section: Optional[str] = None) -> str:
        """Ouvre la fiche d'un projet actif, et surligne éventuellement une section.

        Args:
            slug: slug exact du projet (liste des projets actifs)
            section: "overview", "problem", "approach", "features", "results" ou "gallery"
        """
        target = f"project-{section.strip()}" if section else "project-detail"
        return _add([{"op": "open_project", "slug": (slug or "").strip()}, {"op": "focus", "target": target}])

    @tool
    async def prepare_contact_message(name: str, contact: str, message: str) -> str:
        """Prépare (sans l'envoyer) un message du visiteur pour Jordan et renvoie le récapitulatif à faire confirmer.

        Args:
            name: nom du visiteur
            contact: courriel OU numéro de téléphone du visiteur
            message: ce que le visiteur veut transmettre
        """
        return contact_service.prepare(ctx.session_id, name, contact, message)

    @tool
    async def send_contact_message() -> str:
        """Envoie à Jordan le message préparé — seulement après la confirmation explicite du visiteur."""
        return await contact_service.send(ctx.session_id, ctx.user_message)

    return [set_site_theme, navigate_site, open_project, prepare_contact_message, send_contact_message]


# =============================================================================
# CONSTRUCTION DE L'AGENT
# =============================================================================

def _system_message(project_lines: list[str]) -> SystemMessage:
    """
    Prompt système en un bloc marqué cache_control : identique d'un appel à
    l'autre (il ne change que si la liste des projets actifs change), donc
    relu depuis le cache à chaque tour de la boucle ReAct.
    """
    projects = "\n".join(project_lines) or "(aucun projet actif)"
    text = AGENT_SYSTEM_PROMPT + "\n" + ACTIONS_PROMPT.replace("{projects}", projects)
    return SystemMessage(content=[{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}])


async def _project_lines() -> list[str]:
    rows = await canonical.fetch_or_empty("projects")
    return [f"- {r.get('titre')} — {r.get('slug')}" for r in rows if r.get("slug")]


async def _prepare(question: str, session_id: str, history: list, rephrased: str,
                   site: Optional[dict], actions: Optional[list]):
    """Agent + messages + config d'une requête (outils liés à la session)."""
    contact_service.start_turn(session_id)
    ctx = TurnContext(
        session_id=session_id,
        user_message=question,
        site=site or {},
        slugs=await canonical.get_active_slugs(),
        actions=actions if actions is not None else [],
    )
    agent = create_react_agent(
        model=_get_agent_llm(),
        tools=LOCAL_TOOLS + _request_tools(ctx),
        prompt=_system_message(await _project_lines()),
    )
    messages = _build_messages(history, rephrased + _site_note(ctx.site))
    return agent, messages, _run_config(question, rephrased, session_id)


def _build_messages(history: list, rephrased: str) -> list[dict]:
    messages = []
    for msg in (history or [])[-6:]:
        role = "user" if msg["role"] == "user" else "assistant"
        messages.append({"role": role, "content": msg["content"]})
    # Pas deux fins de réponse d'affilée par une question (consigne non visible du visiteur)
    if last_answer_asked(history):
        rephrased += ("\n\n(Consigne : ta réponse précédente finissait par une question ; "
                      "ne termine pas celle-ci par une question.)")
    messages.append({"role": "user", "content": rephrased})
    return messages


def _run_config(question: str, rephrased: str, session_id: str) -> RunnableConfig:
    return RunnableConfig(
        run_name="RAG_Agent",
        tags=["agent", "production", session_id],
        metadata={
            "question": question[:120],
            "rephrased": rephrased[:120],
            "session_id": session_id,
        },
    )


# =============================================================================
# POINT D'ENTRÉE STREAMING (utilisé par /chat/)
# =============================================================================

async def stream_rag_agent(
    question: str,
    session_id: str = "anonymous",
    history: list = None,
    rephrased_question: str = "",
    site: Optional[dict] = None,
    actions: Optional[list] = None,
):
    """
    Lance l'agent et renvoie le texte de sa réponse au fil de l'eau
    (stream_mode="messages" : tokens du LLM dès qu'ils arrivent).

    actions : liste remplie par les outils d'action (thème, navigation) ;
    l'appelant en tire la ligne [[guide]] une fois le flux terminé.
    site : contexte envoyé par le front (thème actuel, page actuelle).
    """
    rephrased = rephrased_question or await rephrase_question_async(question, history or [])
    logger.info(f"[stream_rag_agent] question reformulée: '{rephrased[:80]}'")

    agent, messages, config = await _prepare(question, session_id, history, rephrased, site, actions)
    last_msg_id = None
    async for chunk, meta in agent.astream({"messages": messages}, config=config, stream_mode="messages"):
        # On ne diffuse que la sortie du LLM (pas les résultats d'outils)
        if meta.get("langgraph_node") != "agent" or not isinstance(chunk, AIMessageChunk):
            continue
        text = _extract_text(chunk.content)
        if not text:
            continue
        # Nouveau message IA (après un appel d'outil) → séparer du précédent
        if last_msg_id is not None and chunk.id != last_msg_id:
            yield "\n\n"
        last_msg_id = chunk.id
        yield text


# =============================================================================
# POINT D'ENTRÉE NON-STREAMING (évaluation : app/evaluation/run_baseline.py)
# =============================================================================

async def run_rag_agent(
    question: str,
    session_id: str = "anonymous",
    history: list = None,
    rephrased_question: str = "",
    site: Optional[dict] = None,
) -> dict:
    """
    Lance le pipeline RAG agentique et renvoie la réponse complète + le
    contexte récupéré par les outils (utile pour l'évaluation RAGAS).
    """
    rephrased = rephrased_question or await rephrase_question_async(question, history or [])
    logger.info(f"[run_rag_agent] question reformulée: '{rephrased[:80]}'")

    actions: list = []
    agent, messages, config = await _prepare(question, session_id, history, rephrased, site, actions)
    result = await agent.ainvoke({"messages": messages}, config=config)
    final_messages = result.get("messages", [])

    answer = ""
    for msg in reversed(final_messages):
        if hasattr(msg, "type") and msg.type == "ai" and msg.content:
            if not getattr(msg, "tool_calls", []):
                answer = _extract_text(msg.content)
                if answer:
                    break

    tool_messages = [m for m in final_messages if getattr(m, "type", None) == "tool"]
    context = "\n\n---\n\n".join(_extract_text(m.content) for m in tool_messages if m.content)
    logger.info(f"[run_rag_agent] tools_called={len(tool_messages)} answer_len={len(answer)} context_len={len(context)}")

    return {
        "rephrased_question": rephrased,
        "context": context,
        "answer": answer,
        "intent": "AGENT",
        "sources_count": len(tool_messages),
        "actions": actions,
    }
