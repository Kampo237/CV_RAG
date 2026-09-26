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
    r"\b(montre\w*|affiche\w*|ouvre\w*|ouvrir|voir|va sur|vas sur|va a|vas a|aller|allons|"
    r"emm?e+nn?e\w*|amm?e+nn?e\w*|mene(-| )moi|conduis\w*|redirig\w*|dirige\w*|"
    r"ou (est|sont|se trouve|trouver|je trouve|puis-je)|page|telecharg\w*|lien|"
    r"show|open|where|take me|go to)\b"
)
_GREETING = re.compile(
    r"^(bonjour|bonsoir|salut|allo|hello|hi|hey|coucou|yo)"
    r"( (toi|jordan|a toi|tout le monde|a tous))?[\s!.,?]*$"
)
_THEME_DARK = re.compile(r"\b(mode|theme|affichage|fond) (sombre|nuit|noir|dark)\b|\bdark( mode)?\b|\bassombri\w*")
_THEME_LIGHT = re.compile(r"\b(mode|theme|affichage|fond) (clair|jour|blanc|light)\b|\blight mode\b|\beclairci\w*")
_ABOUT_ME = re.compile(
    r"\b(a propos de toi|parle(-| )moi de toi|parle de toi|qui es(-| )tu|presente(-| )toi|"
    r"te presenter|tu es qui|toi c'est qui|dis(-| )moi qui tu es)\b"
)
_LANGUAGES = re.compile(r"\b(langues?|parles(-| )tu|tu parles|bilingue)\b")
_CERTIFICATIONS = re.compile(r"\b(certifications?|certifie\w*|pl-?900|power platform fundamentals)\b")
_DISTINCTIONS = re.compile(r"\b(distinctions?|prix|recompenses?|permis|hackathons?|mchacks|mpchacks|mentorat|mentor)\b")
_VALUES = re.compile(r"\b(valeurs|qualites)\b")
_INTERESTS = re.compile(r"\b(interets?|centres? d'interet|passions?|loisirs|hobbies?)\b")
_BEST_PROJECTS = re.compile(
    r"\b(meilleurs?|principaux|phares?|preferes?|favoris?|top|plus importants?)( \w+)? (projets?|realisations?)\b"
    r"|\b(projets?|realisations?) (phares?|preferes?|favoris?|principaux|mis en avant)\b"
)
# Sections d'une fiche projet (ancres du site)
_PROJECT_SECTIONS = [
    ("project-problem", re.compile(r"\b(probleme|problematique|defi|enjeu|besoin)\b")),
    ("project-approach", re.compile(r"\b(approche|methode|architecture|conception|comment (tu l'as|as-tu|il a ete|c'est|l'as-tu) \w+)\b")),
    ("project-features", re.compile(r"\b(fonctionnalites?|features?|que fait|ce que fait)\b")),
    ("project-results", re.compile(r"\b(resultats?|impact|bilan|metriques?)\b")),
    ("project-gallery", re.compile(r"\b(captures?|screenshots?|galerie|images?|photos?)\b")),
    ("project-overview", re.compile(r"\b(vue d'ensemble|apercu|resume)\b")),
]
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
    kind: str                 # greeting | theme | about_me | cv | languages | certifications |
                              # distinctions | about | approach | values | interests | contact |
                              # testimonials | skills | experiences | education | projects | project
    navigate: bool = False    # le visiteur demande de montrer / ouvrir / aller
    slug: str = ""            # kind == "project" : slug réel en base
    current: bool = False     # kind == "experiences" : seulement le poste actuel
    section: str = ""         # kind == "project" : ancre de section (project-problem…)
    featured: bool = False    # kind == "projects" : seulement les projets mis en avant
    mode: str = ""            # kind == "theme" : light | dark


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

    if _GREETING.search(q):
        return FastRoute("greeting")
    if _THEME_DARK.search(q):
        return FastRoute("theme", navigate=True, mode="dark")
    if _THEME_LIGHT.search(q):
        return FastRoute("theme", navigate=True, mode="light")

    # Noms de projets retirés avant les tests de mots-clés : sinon « CV Chatbot
    # RAG » déclencherait la route CV.
    rows = await canonical.fetch_or_empty("projects")
    aliases = _project_aliases(rows)
    named = [slug for slug, rx in aliases.items() if rx.search(q)]
    q_rest = q
    for rx in aliases.values():
        q_rest = rx.sub(" ", q_rest)

    # Sections du CV : avant la route CV, sinon « les langues de ton CV »
    # ouvrirait le téléchargement du PDF.
    if not named:
        if _LANGUAGES.search(q_rest):
            return FastRoute("languages", navigate=nav)
        if _CERTIFICATIONS.search(q_rest):
            return FastRoute("certifications", navigate=nav)
        if _DISTINCTIONS.search(q_rest):
            return FastRoute("distinctions", navigate=True)

    if _CV.search(q_rest) and (nav or _PDF.search(q_rest) or words <= 4):
        return FastRoute("cv", navigate=True)
    if _PDF.search(q_rest) and words <= 8:
        return FastRoute("cv", navigate=True)
    if _ABOUT_ME.search(q):
        return FastRoute("about_me", navigate=nav)
    if nav and _ABOUT.search(q):
        return FastRoute("about", navigate=True)
    if nav and _APPROACH.search(q) and not named:
        return FastRoute("approach", navigate=True)
    # Réponse fixe seulement pour une demande courte de navigation ; une demande
    # qui ajoute une vraie question (« … et parle-moi de ce qui te motive ») va à l'agent.
    if nav and _VALUES.search(q) and words <= 8:
        return FastRoute("values", navigate=True)
    if nav and _INTERESTS.search(q) and words <= 8:
        return FastRoute("interests", navigate=True)

    if _CONTACT_HOW.search(q):
        return FastRoute("contact", navigate=nav)

    # Section d'un projet précis (problème, approche…) : avant le filtre
    # qualitatif, qui contient « comment » et « problème ».
    if len(named) == 1:
        for anchor, rx in _PROJECT_SECTIONS:
            if rx.search(q_rest):
                return FastRoute("project", navigate=nav, slug=named[0], section=anchor)
    if not named and _BEST_PROJECTS.search(q) and not re.search(r"\b(pourquoi|why)\b", q):
        return FastRoute("projects", navigate=nav, featured=True)

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

_FAST_SYSTEM = """Tu es l'assistant du portfolio de Yann Willy Jordan Pokam Teguia. Son prénom d'usage est
JORDAN (jamais « Yann » pour te présenter). Tu INCARNES Jordan : première personne (je, mon, mes), tutoiement, ton
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
- Témoignages et personnes citées : n'attribue jamais de genre (pas de « il » / « elle ») ;
  reprends le nom, ou tourne la phrase autrement.
- Ne dis jamais que tu ne peux pas naviguer, ouvrir une page ou changer l'apparence du site :
  le site s'en charge.
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
    if profile.get("telephone"):
        # Public sur le CV et le site ; affiché tel quel, jamais transmis au LLM
        lines.append(f"- **Téléphone** : {profile['telephone']}")
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

    if route.kind == "greeting":
        profile = await canonical.get_profile()
        name = profile.get("surnom") or "Jordan"
        title = profile.get("titre_professionnel")
        who = f"Moi c'est {name}, {title.lower()}" if title else f"Moi c'est {name}"
        return FastAnswer(_once(f"Salut ! 👋 {who}. Pose-moi tes questions sur mes projets, mon parcours ou "
                                "mes compétences — je peux aussi te guider dans le site."), "", "greeting")

    if route.kind == "theme":
        text_ = ("Voilà, le site passe en mode sombre 🌙" if route.mode == "dark"
                 else "Voilà, le site passe en mode clair ☀️")
        return FastAnswer(_once(text_), guide({"op": "set_theme", "mode": route.mode}), f"theme:{route.mode}")

    if route.kind == "about_me":
        profile = await canonical.get_profile()
        if not profile:
            return None
        nav_line = guide({"op": "navigate", "path": "/about"},
                         {"op": "focus", "target": "about-intro"}) if route.navigate else ""
        hint = _nav_hint("ma page À propos") if route.navigate else ""
        hint += "Le visiteur veut me connaître : présente-moi en 2 à 4 phrases à partir du profil.\n\n"
        return FastAnswer(_stream_llm(question, "Profil :\n" + _llm_data([profile]), history, hint),
                          nav_line, "about_me")

    if route.kind == "languages":
        skills = await canonical.fetch_or_empty("skills")
        langs = [r for r in skills if (r.get("categorie") or "").lower() == "langues"]
        nav_line = guide({"op": "navigate", "path": "/cv"}, {"op": "focus", "target": "cv-languages"})
        if not langs:
            return FastAnswer(_once("Mes langues sont indiquées sur la page CV 🌍"), nav_line, "languages:page")
        parts = [f"{r['nom'].lower()} ({(r.get('description') or '').lower()})" if r.get("description")
                 else r["nom"].lower() for r in langs]
        spoken = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " et " + parts[-1]
        return FastAnswer(_once(f"Je parle {spoken} 🌍"), nav_line if route.navigate else "", "languages")

    if route.kind == "certifications":
        rows = canonical.annotate_formations(await canonical.fetch_or_empty("education"))
        certs = [r for r in rows if re.search(r"certif|pl-?900", normalize(r.get("titre", "")))]
        nav_line = guide({"op": "navigate", "path": "/cv"}, {"op": "focus", "target": "cv-certifications"})
        if not certs:
            return FastAnswer(_once("Mes certifications sont indiquées sur la page CV 📜"), nav_line, "certifications:page")
        lines = [f"- **{r['titre']}** — {r['statut']}" + (f" : {r['description']}" if r.get("description") else "")
                 for r in certs]
        return FastAnswer(_once("Côté certifications 📜\n\n" + "\n".join(lines)),
                          nav_line if route.navigate else "", "certifications")

    if route.kind == "distinctions":
        # Pas de table en base pour les permis et distinctions : on renvoie vers
        # la section du CV, en citant seulement ce qui est en base (projets).
        projects = await canonical.fetch_or_empty("projects")
        mentions = [f"{r['titre']} : {res}" for r in projects
                    for res in (r.get("resultats") or []) if isinstance(res, str) and "mention" in res.lower()]
        text_ = "Voici mes permis et distinctions, sur la page CV 🏅"
        if mentions:
            text_ += "\n\nParmi eux : " + " ; ".join(mentions)
        return FastAnswer(_once(text_), guide({"op": "navigate", "path": "/cv"},
                                              {"op": "focus", "target": "cv-distinctions"}), "distinctions")

    if route.kind in ("values", "interests"):
        target, text_ = (("about-values", "Voici mes valeurs 🤝") if route.kind == "values"
                         else ("about-interests", "Voici mes centres d'intérêt ✨"))
        return FastAnswer(_once(text_), guide({"op": "navigate", "path": "/about"},
                                              {"op": "focus", "target": target}), route.kind)

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
        selected = [r for r in rows if r.get("est_mis_en_avant")] if route.featured else rows
        selected = selected or rows
        label = "Projets mis en avant (mes meilleurs projets)" if route.featured else "Projets actifs du portfolio"
        data = f"{label} :\n" + "\n".join(canonical.format_project_line(r) for r in selected)
        hint = _nav_hint("la grille des projets") if route.navigate else ""
        if route.featured:
            hint += "Présente ces projets mis en avant comme mes meilleurs projets.\n\n"
        nav_line = guide({"op": "navigate", "path": "/projects"},
                         {"op": "focus", "target": "projects-grid"}) if route.navigate else ""
        return FastAnswer(_stream_llm(question, data, history, hint), nav_line,
                          "projects:featured" if route.featured else "projects")

    row = next((r for r in rows if r.get("slug") == route.slug), None)
    if row is None:
        return None
    section_names = {"project-problem": "le problème de départ", "project-approach": "l'approche",
                     "project-features": "les fonctionnalités", "project-results": "les résultats",
                     "project-gallery": "les captures", "project-overview": "la vue d'ensemble"}
    target = route.section or "project-detail"
    hint = _nav_hint(f"{section_names.get(route.section, 'la fiche')} de ce projet") if route.navigate else ""
    if route.section:
        hint += (f"Le visiteur s'intéresse à {section_names[route.section]} de ce projet : concentre-toi "
                 "dessus, en t'en tenant STRICTEMENT à ce que disent les données. Si elles ne le décrivent "
                 "pas explicitement, résume ce qui existe sans extrapoler ni ajouter de détails.\n\n")
    nav_line = guide({"op": "open_project", "slug": route.slug},
                     {"op": "focus", "target": target}) if route.navigate else ""
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
