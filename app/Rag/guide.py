"""
Guidage du site — ligne d'action [[guide]]
(cf. GUIDE_BACKEND_PROMPT.md et BACKEND_NEON_SOURCE_DE_VERITE.md §2)

Le front coupe la dernière ligne `[[guide]]{"actions":[...]}` avant
l'affichage markdown et exécute les actions (navigate / open_project / focus).

Ce module :
  - liste les routes et cibles fixes du site ;
  - valide les slugs contre les projets ACTIFS de portfolio_app_projet
    (slug en base = segment /projects/:slug, jamais inventé) ;
  - fournit la section de prompt à injecter dans les prompts système LLM ;
  - filtre un flux de tokens pour intercepter la ligne [[guide]] et la
    ré-émettre validée à la fin, sans jamais l'afficher au visiteur.
"""
import json
import logging
from typing import Iterable, Optional

logger = logging.getLogger("rag_pipeline")

GUIDE_MARKER = "[[guide]]"
MAX_ACTIONS = 3

GUIDE_PATHS = {"/", "/about", "/projects", "/cv", "/testimonials"}

# Cibles fixes (data-guide) ; les cartes "project-<slug>" sont validées à part
GUIDE_TARGETS = {
    "home-hero", "home-about", "home-projects", "home-approach", "home-stats",
    "home-contact", "site-nav", "about-intro", "about-skills", "projects-grid",
    "project-detail", "cv-download", "cv-experience", "cv-education", "testimonials-list",
}


# =============================================================================
# SECTION DE PROMPT
# =============================================================================

def guide_prompt(project_lines: Iterable[str]) -> str:
    """
    Section de prompt « guidage ». `project_lines` : une ligne par projet actif
    (titre + slug réel), pour que le modèle copie le slug au lieu de l'inventer.
    """
    projects = "\n".join(project_lines) or "(aucun projet actif — n'utilise pas open_project)"
    return f"""────────────────────────────────────────
## GUIDAGE DANS LE SITE
────────────────────────────────────────

Tu peux guider le visiteur dans le site, sans jamais prétendre avoir cliqué
toi-même dans le navigateur.

Quand la question demande de montrer, ouvrir, aller vers ou retrouver quelque
chose qui existe sur le site, réponds d'abord en une ou deux phrases, puis
termine par une seule ligne d'action. Cette ligne est une instruction pour le site.

Format exact, dernière ligne du message, rien après :
[[guide]]{{"actions":[ ... ]}}

Règles :
- Maximum 3 actions, dans l'ordre d'exécution.
- N'utilise que les opérations, routes, cibles et slugs listés ici. N'invente rien.
- Jamais d'URL externe, de mailto ni de soumission de formulaire.
- Question purement conversationnelle → pas de ligne [[guide]].
- Tu hésites entre deux cibles → demande une précision, pas de ligne [[guide]].
- Tu peux répondre sans page du site (le détail est déjà dans les données) → réponds, pas de ligne [[guide]].
- Le texte visible ne contient pas le JSON, pas le mot "guide", et ne décrit pas le format technique.

Opérations :
- {{"op":"navigate","path":"/about"}} — path parmi : /  /about  /projects  /cv  /testimonials
- {{"op":"open_project","slug":"<slug>"}} — slug copié EXACTEMENT de la liste des projets actifs ci-dessous
- {{"op":"focus","target":"<cible>"}} — project-detail exige un open_project avant

Correspondances :
- Liste des projets → navigate /projects puis focus projects-grid
- Un projet précis → open_project <slug> puis focus project-detail
- CV ou PDF → navigate /cv puis focus cv-download si le PDF est connu, sinon cv-experience
- Expérience → navigate /cv puis focus cv-experience
- Formation → navigate /cv puis focus cv-education
- Compétences → navigate /about puis focus about-skills
- Contact → navigate / puis focus home-contact
- Témoignages → navigate /testimonials puis focus testimonials-list
- Façon de travailler → navigate / puis focus home-approach

Autres cibles : home-hero, home-about, home-projects, home-stats, site-nav,
about-intro, project-<slug> (carte d'un projet sur /projects).

Projets actifs (titre — slug) :
{projects}

Exemple — « Montre-moi tes compétences » → une phrase, puis
[[guide]]{{"actions":[{{"op":"navigate","path":"/about"}},{{"op":"focus","target":"about-skills"}}]}}"""


# =============================================================================
# VALIDATION
# =============================================================================

def validate_actions(actions, allowed_slugs: Iterable[str]) -> list[dict]:
    """
    Garde uniquement les actions connues du site, dans l'ordre, max 3.
    Les slugs (open_project, cartes project-<slug>) doivent être ceux des
    projets actifs en base. project-detail n'est gardé qu'après un open_project.
    """
    if not isinstance(actions, list):
        return []

    slugs = set(allowed_slugs or ())
    clean: list[dict] = []
    project_opened = False
    for action in actions:
        if not isinstance(action, dict):
            continue
        op, target = action.get("op"), action.get("target")
        if op == "navigate" and action.get("path") in GUIDE_PATHS:
            clean.append({"op": "navigate", "path": action["path"]})
        elif op == "open_project" and action.get("slug") in slugs:
            clean.append({"op": "open_project", "slug": action["slug"]})
            project_opened = True
        elif op == "focus" and isinstance(target, str) and (
            target in GUIDE_TARGETS or (target.startswith("project-") and target[8:] in slugs)
        ):
            if target == "project-detail" and not project_opened:
                continue
            clean.append({"op": "focus", "target": target})
        else:
            logger.warning(f"[guide] action rejetée: {action}")
        if len(clean) >= MAX_ACTIONS:
            break
    return clean


def build_guide_line(actions: list[dict], allowed_slugs: Iterable[str] = ()) -> str:
    """Ligne finale `[[guide]]{...}` (sans saut de ligne), ou "" si rien de valide."""
    actions = validate_actions(actions, allowed_slugs)
    if not actions:
        return ""
    return GUIDE_MARKER + json.dumps({"actions": actions}, ensure_ascii=False, separators=(",", ":"))


def parse_guide_payload(raw: str, allowed_slugs: Iterable[str]) -> list[dict]:
    """Parse le JSON qui suit le marqueur (tolère du texte parasite après l'objet)."""
    raw = (raw or "").strip()
    if not raw.startswith("{"):
        return []
    try:
        payload, _ = json.JSONDecoder().raw_decode(raw)
    except json.JSONDecodeError:
        logger.warning(f"[guide] JSON invalide: {raw[:120]}")
        return []
    return validate_actions(payload.get("actions") if isinstance(payload, dict) else None, allowed_slugs)


# =============================================================================
# FILTRE DE FLUX
# =============================================================================

class GuideStreamFilter:
    """
    Intercepte la ligne [[guide]] dans un flux de tokens LLM.

    feed(chunk) renvoie le texte affichable immédiatement. Tout ce qui suit le
    marqueur est retenu ; un début de marqueur coupé entre deux chunks
    ("[[gu" + "ide]]") est gardé en attente le temps de trancher.
    finish() renvoie le reste affichable et la ligne [[guide]] validée (ou "").
    """

    def __init__(self, allowed_slugs: Iterable[str] = ()):
        self._slugs = set(allowed_slugs or ())
        self._tail = ""
        self._captured: Optional[str] = None

    def feed(self, chunk: str) -> str:
        if self._captured is not None:
            self._captured += chunk
            return ""

        text = self._tail + chunk
        idx = text.find(GUIDE_MARKER)
        if idx >= 0:
            self._captured = text[idx + len(GUIDE_MARKER):]
            self._tail = ""
            return text[:idx]

        keep = 0
        for k in range(min(len(GUIDE_MARKER) - 1, len(text)), 0, -1):
            if GUIDE_MARKER.startswith(text[-k:]):
                keep = k
                break
        self._tail = text[-keep:] if keep else ""
        return text[:-keep] if keep else text

    def finish(self) -> tuple[str, str]:
        if self._captured is None:
            return self._tail, ""
        return "", build_guide_line(parse_guide_payload(self._captured, self._slugs), self._slugs)


def guide_suffix(visible_text: str, guide_line: str) -> str:
    """Ligne [[guide]] précédée d'un saut de ligne si le texte n'en finit pas déjà par un."""
    if not guide_line:
        return ""
    return guide_line if visible_text.endswith("\n") else "\n" + guide_line
