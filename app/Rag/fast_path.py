"""
Chemin rapide — questions de portfolio sans agent ReAct
(cf. BACKEND_NEON_SOURCE_DE_VERITE.md §3)

Pour « quels sont tes projets », « ouvre SafetyHub », « où est le CV »,
« comment te contacter », « tu connais Docker ? »… :
  1. routeur léger (regex, aucun appel LLM, aucune reformulation) ;
  2. lignes des tables canoniques (SQL écrit à la main, en cache — canonical.py) ;
  3. au plus UN appel LLM (Haiku) qui streame vraiment — ou un texte fixe,
     sans aucun appel, quand la réponse n'a besoin d'aucune donnée.

La ligne [[guide]] est construite ici par le code, avec les slugs réels de
portfolio_app_projet : elle est donc toujours valide.

Tout ce qui ne matche pas clairement — ou dont la table canonique est encore
vide — retombe sur le pipeline normal (agent). Le routeur est conservateur.
"""
import os
import re
import logging
import datetime
import unicodedata
from dataclasses import dataclass
from typing import AsyncIterator, Optional

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage

from app.Rag import canonical
from app.Rag.guide import build_guide_line

logger = logging.getLogger("rag_pipeline")


# =============================================================================
# NORMALISATION + MOTIFS
# =============================================================================

def normalize(text_: str) -> str:
    """Minuscules, sans accents, apostrophes unifiées, espaces compactés."""
    s = unicodedata.normalize("NFKD", (text_ or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("’", "'").replace("`", "'")
    return re.sub(r"\s+", " ", s).strip()


_NAV = re.compile(
    r"\b(montre\w*|affiche\w*|ouvre\w*|ouvrir|voir|va sur|aller|emmene\w*|amene\w*|"
    r"redirige\w*|dirige\w*|ou (est|sont|se trouve|trouver|je trouve|puis-je)|"
    r"telecharg\w*|lien|show|open|where)\b"
)
_CV = re.compile(r"\b(cv|curriculum( vitae)?)\b")
_PDF = re.compile(r"\bpdf\b")
_TESTIMONIALS = re.compile(r"\b(temoignages?|avis|recommandations?|testimonials?)\b")
_ABOUT = re.compile(r"\b(a propos|page about)\b")
_APPROACH = re.compile(r"\b(facon de travailler|methode de travail|ta methode|ton approche|comment tu travailles)\b")
_PROJECTS = re.compile(r"\b(projets?|projects?|realisations?|portfolio)\b")
_CONTACT_HOW = re.compile(r"comment (puis-je |je peux |on peut )?(te |vous )?(contacter|joindre|ecrire)")
_CONTACT = re.compile(r"\b(contact\w*|joindre|e-?mail|courriel|linkedin|github|disponib\w*)\b")
_SKILLS = re.compile(
    r"\b(tu connais|connais-tu|tu maitrises|maitrises-tu|tu utilises|utilises-tu|"
    r"as-tu (deja )?(utilise|travaille avec|fait du)|t'as (deja )?(utilise|fait du)|"
    r"(de l')?experience (en|avec)|ton niveau|niveau en|competences?|technos?|"
    r"technologies|langages?|frameworks?|stack|skills?)\b"
)
# « Où travailles-tu ? », « ton poste actuel » → seulement le poste principal
_CURRENT_JOB = re.compile(
    r"\b(ou travailles|tu travailles ou|travailles-tu|tu bosses|bosses-tu|"
    r"(poste|emploi|job|travail) actuel|actuellement|en ce moment|que fais-tu dans la vie)\b"
)
_WORK = re.compile(r"\b(travaill\w*|bosse\w*|poste|emploi|job|metier|fais-tu dans la vie)\b")
_EXPERIENCE = re.compile(r"\b(experiences?|emplois?|stages?|ou as-tu travaille|entreprises?|postes?)\b")
_EDUCATION = re.compile(r"\b(formations?|etudes|diplomes?|cegep|universite|ecole|education)\b")
# Questions qui demandent du récit / du jugement → agent (vector store + outils)
_QUALITATIVE = re.compile(
    r"\b(pourquoi|comment|meilleur\w*|prefere\w*|fier|appris|difficile\w*|defis?|"
    r"challenges?|problemes?|compare\w*|difference\w*|conseils?|idees?|why|how)\b"
)
_SMS = re.compile(
    r"\b(sms|textos?|text message)\b|transmet\w*|laisse[rz]? (un )?(message|mot)|"
    r"envoie[rz]? (lui |a jordan |a yann |un )?(message|mot)|"
    r"contacter (directement )?(jordan|yann)|lui ecrire"
)
_SMS_FLOW = re.compile(r"tu confirmes|texto|sms|transmet|courriel|adresse e-?mail")

# Alias en plus du titre et du slug lus en base (appliqués seulement si le
# slug existe parmi les projets actifs).
EXTRA_ALIASES: dict[str, list[str]] = {
    "super-cchic": ["super chic", "superchic"],
    "cv-chatbot-rag": ["chatbot", "chatbot rag"],
    "wpf-manager": ["gestionnaire wpf", "projet wpf", "wpf", "webnet", "gestionnaire de projet webnet"],
    "ecrin-de-julias": ["ecrin de julia", "ecrin", "julia's", "julias"],
}


# =============================================================================
# ALERTES AUTONOMES (remplacent le send_sms proactif de l'agent : zéro LLM)
# =============================================================================

_ALERT_RULES = [
    ("LEAD", re.compile(
        r"\b(recrut\w*|embauch\w*|offre (d'emploi|de stage)|entretien d'embauche|"
        r"on cherche un (dev\w*|stagiaire|programmeur))\b")),
    ("PROJET", re.compile(r"\b(devis|freelance|tarifs?)\b|j'ai un projet|combien (tu )?(coutes?|factures?|charges?)")),
    ("ALERTE", re.compile(
        r"ignore (tes|les|toutes|all|previous)\b|system prompt|prompt systeme|"
        r"api[ _-]?key|cle api|mot de passe|jailbreak")),
]


def detect_alert(question: str) -> Optional[str]:
    """Libellé d'alerte (LEAD / PROJET / ALERTE) si la question en déclenche une."""
    q = normalize(question)
    for label, pattern in _ALERT_RULES:
        if pattern.search(q):
            return label
    return None


def wants_sms(question: str, history: list[dict]) -> bool:
    """
    True si le visiteur demande explicitement à transmettre un message, ou si
    la conversation est déjà dans le protocole SMS (collecte nom/email,
    confirmation). Seul ce cas justifie d'ouvrir la connexion MCP.
    """
    if _SMS.search(normalize(question)):
        return True
    for msg in reversed(history or []):
        if msg.get("role") == "assistant":
            return bool(_SMS_FLOW.search(normalize(str(msg.get("content", "")))))
    return False


# =============================================================================
# ROUTEUR
# =============================================================================

@dataclass
class FastRoute:
    kind: str                 # cv | testimonials | about | approach | contact |
                              # skills | experiences | education | projects | project
    navigate: bool = False    # le visiteur demande de montrer / ouvrir
    slug: str = ""            # pour kind == "project" (slug réel en base)
    current: bool = False     # pour kind == "experiences" : seulement le poste actuel


def _project_aliases(rows: list[dict]) -> dict[str, re.Pattern]:
    aliases: dict[str, re.Pattern] = {}
    for row in rows:
        slug = row.get("slug")
        if not slug:
            continue
        names = {normalize(row.get("titre", "")), slug, slug.replace("-", " "), slug.replace("-", "")}
        names.update(EXTRA_ALIASES.get(slug, []))
        names.discard("")
        aliases[slug] = re.compile(r"\b(" + "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True)) + r")\b")
    return aliases


async def route_question(question: str) -> Optional[FastRoute]:
    """Routeur sans LLM. None → pipeline normal."""
    q = normalize(question)
    if not q or _SMS.search(q):
        return None

    words = len(q.split())
    nav = bool(_NAV.search(q))

    # Noms de projets retirés avant les tests de mots-clés : sinon « CV Chatbot
    # RAG » déclencherait la route CV.
    rows = await canonical.fetch_or_empty("projects")
    aliases = _project_aliases(rows)
    named = [slug for slug, rx in aliases.items() if rx.search(q)]
    q_rest = q
    for rx in aliases.values():
        q_rest = rx.sub(" ", q_rest)

    # Pages : aucune donnée nécessaire
    if _CV.search(q_rest) and (nav or _PDF.search(q_rest) or words <= 4):
        return FastRoute("cv", navigate=True)
    if _PDF.search(q_rest) and words <= 8:
        return FastRoute("cv", navigate=True)
    if nav and _ABOUT.search(q):
        return FastRoute("about", navigate=True)
    if nav and _APPROACH.search(q):
        return FastRoute("approach", navigate=True)

    if _CONTACT_HOW.search(q):
        return FastRoute("contact", navigate=nav)
    if _QUALITATIVE.search(q):
        return None

    if len(named) > 1:
        return None
    if len(named) == 1:
        return FastRoute("project", navigate=nav, slug=named[0])

    if _CURRENT_JOB.search(q) and _WORK.search(q):
        return FastRoute("experiences", navigate=nav, current=True)
    if _TESTIMONIALS.search(q):
        return FastRoute("testimonials", navigate=nav)
    if _CONTACT.search(q):
        return FastRoute("contact", navigate=nav)
    if _SKILLS.search(q):
        return FastRoute("skills", navigate=nav)
    if _EDUCATION.search(q):
        return FastRoute("education", navigate=nav)
    if _EXPERIENCE.search(q):
        return FastRoute("experiences", navigate=nav)
    if _PROJECTS.search(q):
        return FastRoute("projects", navigate=nav)
    return None


# =============================================================================
# GÉNÉRATION — un seul appel Haiku en streaming
# =============================================================================

_FAST_SYSTEM = """Tu es l'assistant du portfolio de Yann Willy Jordan Pokam Teguia, développeur
logiciel. Tu INCARNES Yann : première personne (je, mon, mes), tutoiement, ton
chaleureux et humble (jamais "expert", jamais "je maîtrise parfaitement").

Règles :
- Chaque fait vient UNIQUEMENT des données fournies (lignes de la base du portfolio).
  Jamais de ta mémoire. N'invente rien (dates, technos, résultats, liens).
- Si les données ne contiennent pas la réponse : dis « Je n'ai pas cette information. »
  Ne propose pas de remplacement, ne promets aucun envoi (ni texto, ni courriel).
- Formations : respecte le champ « statut » (terminé / en cours) ; ne présente jamais une
  formation terminée comme en cours.
- Expériences : respecte le champ « statut » tel quel. Un poste sur appel n'est jamais un
  emploi régulier ni un temps partiel ; un emploi secondaire n'est jamais le poste principal.
- 2 à 4 phrases, ou une courte liste à puces s'il y a 4 éléments ou plus.
- 1 à 2 emojis maximum. Markdown léger autorisé.
- Adapte la langue à celle du visiteur.
- Termine par une courte question de relance quand c'est naturel.
- N'écris jamais de ligne technique, de JSON ni le mot "guide"."""

_llm_fast: Optional[ChatAnthropic] = None


def get_fast_llm() -> ChatAnthropic:
    """Singleton : réutilise la connexion HTTP keep-alive vers l'API (TTFT plus court)."""
    global _llm_fast
    if _llm_fast is None:
        _llm_fast = ChatAnthropic(
            model_name="claude-haiku-4-5-20251001",
            temperature=0.3,
            max_tokens=600,
            api_key=os.getenv("ANTHROPIC_API_KEY"),
        )
    return _llm_fast


async def _stream_llm(question: str, data: str, history: list[dict], nav_hint: str) -> AsyncIterator[str]:
    history_text = "\n".join(
        f"{'Visiteur' if m['role'] == 'user' else 'Moi'}: {m['content']}"
        for m in (history or [])[-4:]
    ) or "Aucun."
    human = (
        f"Date du jour : {datetime.date.today().isoformat()}\n\n"
        f"Données (lignes de la base du portfolio) :\n{data}\n\n"
        f"Échanges précédents :\n{history_text}\n\n"
        f"{nav_hint}"
        f"Question du visiteur : {question}"
    )
    async for chunk in get_fast_llm().astream([SystemMessage(_FAST_SYSTEM), HumanMessage(human)]):
        content = chunk.content
        if isinstance(content, list):
            content = "".join(b.get("text", "") for b in content if isinstance(b, dict))
        if content:
            yield content


async def _once(text_: str) -> AsyncIterator[str]:
    yield text_


# Un LLM qui recopie une URL peut la corrompre (observé : un segment dupliqué
# dans l'URL LinkedIn). Ces colonnes ne lui sont donc jamais transmises ; le
# code les ajoute lui-même, telles quelles, quand elles sont utiles.
_NO_LLM_COLUMNS = ("id", "url_github", "url_demo", "image", "photo", "cv_pdf",
                   "email", "linkedin", "github", "portfolio")
_LINK_REQUEST = re.compile(r"\b(github|code|source|repo\w*|depot|liens?|url|demo)\b")


def _llm_data(rows: list[dict]) -> str:
    return canonical.format_rows(rows, skip=_NO_LLM_COLUMNS)


async def _then(stream: AsyncIterator[str], suffix: str) -> AsyncIterator[str]:
    async for chunk in stream:
        yield chunk
    if suffix:
        yield suffix


def _contact_text(profile: dict) -> str:
    """Réponse contact 100 % issue de la ligne de profil (aucun LLM, liens exacts)."""
    lines = []
    if profile.get("email"):
        lines.append(f"- **Email** : {profile['email']}")
    for col, label in (("linkedin", "LinkedIn"), ("github", "GitHub"), ("portfolio", "Portfolio")):
        if profile.get(col):
            lines.append(f"- **{label}** : [{profile[col]}]({profile[col]})")
    if not lines:
        return "Je n'ai pas cette information."
    text_ = "Voici comment me joindre ✉️\n\n" + "\n".join(lines)
    if profile.get("disponible") is True:
        text_ += "\n\nJe suis disponible en ce moment."
    return text_


@dataclass
class FastAnswer:
    stream: AsyncIterator[str]   # texte visible
    guide_line: str              # "" ou "[[guide]]{...}"
    label: str                   # pour les logs


# Intention → (page, cible, libellé des données, phrase si on montre la page sans données)
_SECTIONS = {
    "skills": ("/about", "about-skills", "Compétences", "Voici mes compétences 💻"),
    "experiences": ("/cv", "cv-experience", "Expériences", "Voici mon expérience sur la page parcours 💼"),
    "education": ("/cv", "cv-education", "Formation", "Voici ma formation sur la page parcours 🎓"),
    "testimonials": ("/testimonials", "testimonials-list", "Témoignages approuvés",
                     "Voici les témoignages laissés par les personnes avec qui j'ai travaillé ✨"),
}
_SECTION_TABLE = {"skills": "skills", "experiences": "experiences", "education": "education",
                  "testimonials": "testimonials"}


def _nav_hint(what: str) -> str:
    return (f"Le site affiche en même temps {what} au visiteur : commence par une "
            "formule du type « Voici … », sans décrire de mécanisme technique.\n\n")


async def prepare_fast_answer(route: FastRoute, question: str, history: list[dict]) -> Optional[FastAnswer]:
    """
    Prépare la réponse. None si la table canonique est vide / injoignable ou
    si le projet est introuvable → l'appelant retombe sur le pipeline normal.
    """
    slugs = await canonical.get_active_slugs()

    def guide(*actions) -> str:
        return build_guide_line(list(actions), slugs)

    if route.kind == "cv":
        # Source : portfolio_app_infopersonnelle.cv_pdf. Vide → on ne dit pas
        # qu'il n'existe pas de PDF, on dit qu'on n'a pas l'information.
        cv_pdf = await canonical.get_cv_pdf()
        if cv_pdf:
            return FastAnswer(_once(f"Tu peux télécharger mon CV en PDF ici : [CV en PDF]({cv_pdf}) 📄"),
                              guide({"op": "navigate", "path": "/cv"}, {"op": "focus", "target": "cv-download"}),
                              "cv")
        return FastAnswer(_once("Je n'ai pas l'information sur le PDF de mon CV pour le moment. "
                                "Mon parcours est détaillé sur la page CV 📄"),
                          guide({"op": "navigate", "path": "/cv"}, {"op": "focus", "target": "cv-experience"}),
                          "cv:sans_pdf")

    if route.kind == "about":
        return FastAnswer(_once("Voici ma page À propos 👋"),
                          guide({"op": "navigate", "path": "/about"}, {"op": "focus", "target": "about-intro"}),
                          "about")

    if route.kind == "approach":
        return FastAnswer(_once("Voici comment je travaille 🛠️"),
                          guide({"op": "navigate", "path": "/"}, {"op": "focus", "target": "home-approach"}),
                          "approach")

    if route.kind == "contact":
        profile = await canonical.get_profile()
        if not profile:
            return None
        nav_line = guide({"op": "navigate", "path": "/"},
                         {"op": "focus", "target": "home-contact"}) if route.navigate else ""
        return FastAnswer(_once(_contact_text(profile)), nav_line, "contact")

    if route.kind in _SECTIONS:
        path, target, label, shown = _SECTIONS[route.kind]
        nav_line = guide({"op": "navigate", "path": path}, {"op": "focus", "target": target}) if route.navigate else ""
        rows = await canonical.fetch_or_empty(_SECTION_TABLE[route.kind])
        if not rows:
            if route.navigate:
                # La page existe sur le site même si la table n'est pas encore remplie
                return FastAnswer(_once(shown), nav_line, f"{route.kind}:page")
            logger.info(f"[fast_path] table {route.kind} vide → pipeline normal")
            return None
        hint = _nav_hint("la section correspondante") if route.navigate else ""
        if route.kind == "education":
            rows = canonical.annotate_formations(rows)
        if route.kind == "experiences":
            rows = canonical.annotate_experiences(rows)
            main_jobs = [r for r in rows if canonical.is_main_status(r["statut"])]
            if route.current and main_jobs:
                # Seul le poste principal est transmis : le modèle ne peut pas
                # y mêler les emplois secondaires ou sur appel.
                rows = main_jobs
                hint += ("Le visiteur demande mon poste actuel : présente uniquement ce poste "
                         "principal, sans évoquer d'autres emplois.\n\n")
        data = f"{label} :\n{_llm_data(rows)}"
        return FastAnswer(_stream_llm(question, data, history, hint), nav_line, route.kind)

    rows = await canonical.fetch_or_empty("projects")
    if not rows:
        return None

    if route.kind == "projects":
        data = "Projets actifs du portfolio :\n" + "\n".join(canonical.format_project_line(r) for r in rows)
        hint = _nav_hint("la grille des projets") if route.navigate else ""
        nav_line = guide({"op": "navigate", "path": "/projects"},
                         {"op": "focus", "target": "projects-grid"}) if route.navigate else ""
        return FastAnswer(_stream_llm(question, data, history, hint), nav_line, "projects")

    row = next((r for r in rows if r.get("slug") == route.slug), None)
    if row is None:
        return None
    hint = _nav_hint("la fiche de ce projet") if route.navigate else ""
    nav_line = guide({"op": "open_project", "slug": route.slug},
                     {"op": "focus", "target": "project-detail"}) if route.navigate else ""
    # Liens ajoutés par le code (jamais recopiés par le LLM) si le visiteur en demande
    links = []
    if _LINK_REQUEST.search(normalize(question)):
        if row.get("url_github"):
            links.append(f"- Code : [{row['url_github']}]({row['url_github']})")
        if row.get("url_demo"):
            links.append(f"- Démo : [{row['url_demo']}]({row['url_demo']})")
    suffix = ("\n\n" + "\n".join(links)) if links else ""
    hint += ("Les liens demandés s'affichent juste après ta réponse : n'écris aucune URL, "
             "dis simplement qu'ils sont juste en dessous.\n\n" if links
             else "N'écris aucun lien ni URL.\n\n")
    return FastAnswer(_then(_stream_llm(question, _llm_data([row]), history, hint), suffix),
                      nav_line, f"project:{route.slug}")
