"""
Guidage du site — ligne d'action [[guide]]
(cf. GUIDE_BACKEND_PROMPT.md, BACKEND_NEON_SOURCE_DE_VERITE.md §2 et le
contrat du front : validateur du bundle portfolio.jordan-pokam.dev)

Le front coupe tout à partir de [[guide]], puis exécute le JSON dans l'ordre
(au plus 4 actions). Émettre la ligne = y aller tout de suite.

Ce module :
  - liste les routes et ancres acceptées par le front ;
  - valide les slugs contre les projets ACTIFS de portfolio_app_projet ;
  - fournit la section de prompt à injecter dans les prompts système LLM ;
  - filtre un flux de tokens pour intercepter la ligne [[guide]] et la
    ré-émettre validée à la fin, sans jamais l'afficher au visiteur.
"""
import json
import logging
from typing import Iterable, Optional

logger = logging.getLogger("rag_pipeline")

GUIDE_MARKER = "[[guide]]"
MAX_ACTIONS = 4          # le front tronque au-delà (actions.slice(0, 4))
THEME_MODES = {"light", "dark"}

GUIDE_PATHS = {"/", "/about", "/projects", "/cv", "/testimonials"}   # + /projects/{slug}

# Ancres data-guide du site (hors cartes project-<slug>, validées à part)
GUIDE_TARGETS = {
    "home-hero", "home-about", "home-projects", "home-approach", "home-stats", "home-contact",
    "site-nav", "about-intro", "about-skills", "about-values", "about-interests", "projects-grid",
    "cv-download", "cv-experience", "cv-education", "cv-languages", "cv-distinctions",
    "cv-certifications", "testimonials-list",
}
# Sections d'une fiche projet : ignorées par le front hors d'une fiche ouverte
PROJECT_SECTIONS = {
    "project-detail", "project-overview", "project-problem", "project-approach",
    "project-features", "project-results", "project-gallery",
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
## GUIDAGE DANS LE SITE (navigation et thème)
────────────────────────────────────────

Tu PEUX faire naviguer le visiteur dans le site et changer le thème (clair / sombre) :
le site exécute la ligne d'action que tu écris. Ne dis JAMAIS que tu ne peux pas
naviguer, rediriger, ouvrir une page ou changer l'apparence.

La réponse visible vient d'abord. La dernière ligne, et rien d'autre, est l'ordre
de navigation. Le visiteur ne la voit pas.
[[guide]]{{"actions":[ ... ]}}

Émettre cette ligne, c'est y aller tout de suite : ne demande pas de confirmation
(« Je t'amène voir ? »). Si le visiteur demande d'aller quelque part, de montrer,
d'ouvrir ou de changer le thème, écris la ligne.

Pas de ligne [[guide]] dans trois cas : la réponse suffit, l'endroit n'existe pas sur
le site, ou la demande est ambiguë (alors demande de préciser).

Règles :
- Au plus 4 actions, dans l'ordre d'exécution. Une seule visite (navigate ou open_project).
- N'utilise que les opérations, routes, ancres et slugs listés ici. N'invente rien.
- Jamais d'adresse externe, de mailto ni de formulaire.
- Le texte visible ne contient pas le JSON, pas le mot "guide", et ne décrit pas le format.

Opérations :
- {{"op":"navigate","path":"/about"}} — path parmi : /  /about  /projects  /cv  /testimonials  /projects/<slug>
- {{"op":"focus","target":"<ancre>"}} — défile jusqu'à l'ancre et la surligne
- {{"op":"open_project","slug":"<slug>"}} — ouvre la fiche (slug copié EXACTEMENT de la liste ci-dessous)
- {{"op":"set_theme","mode":"dark"}} — mode "light" ou "dark"

Ancres :
- accueil (/) : home-hero, home-about, home-projects, home-approach, home-stats, home-contact
- partout : site-nav
- /about : about-intro, about-skills, about-values, about-interests
- /projects : projects-grid, project-<slug> (carte d'un projet)
- fiche projet (après open_project) : project-detail, project-overview, project-problem,
  project-approach, project-features, project-results, project-gallery
- /cv : cv-download, cv-experience, cv-education, cv-languages, cv-distinctions, cv-certifications
- /testimonials : testimonials-list
Une section de fiche s'enchaîne après open_project ; seule, elle est ignorée.

Correspondances :
- Liste des projets → navigate /projects puis focus projects-grid
- Un projet → open_project <slug> (puis focus d'une section si demandée :
  problème → project-problem, approche → project-approach, fonctionnalités →
  project-features, résultats → project-results, captures → project-gallery)
- CV ou PDF → navigate /cv puis focus cv-download (sinon cv-experience)
- Expérience / formation / langues / certifications / distinctions → navigate /cv puis
  cv-experience / cv-education / cv-languages / cv-certifications / cv-distinctions
- Compétences / valeurs / centres d'intérêt → navigate /about puis about-skills /
  about-values / about-interests
- Contact → navigate / puis focus home-contact ; façon de travailler → home-approach
- Témoignages → navigate /testimonials puis focus testimonials-list
- Mode sombre / clair → set_theme dark / light

Projets actifs (titre — slug) :
{projects}

Exemples :
« Emmène-moi aux témoignages » → une phrase, puis
[[guide]]{{"actions":[{{"op":"navigate","path":"/testimonials"}},{{"op":"focus","target":"testimonials-list"}}]}}
« Passe en mode sombre » → une phrase, puis
[[guide]]{{"actions":[{{"op":"set_theme","mode":"dark"}}]}}"""


# =============================================================================
# VALIDATION
# =============================================================================

def validate_actions(actions, allowed_slugs: Iterable[str]) -> list[dict]:
    """
    Garde uniquement les actions acceptées par le front, dans l'ordre, max 4 :
    une seule visite (navigate / open_project), slugs = projets actifs en base,
    sections de fiche seulement après ouverture d'un projet.
    """
    if not isinstance(actions, list):
        return []

    slugs = set(allowed_slugs or ())
    clean: list[dict] = []
    visited = False
    project_opened = False
    for action in actions:
        if not isinstance(action, dict):
            continue
        op, target, path = action.get("op"), action.get("target"), action.get("path")

        if op in ("navigate", "open_project") and visited:
            logger.warning(f"[guide] seconde visite ignorée: {action}")
            continue

        if op == "navigate" and isinstance(path, str) and (
            path in GUIDE_PATHS or (path.startswith("/projects/") and path[10:] in slugs)
        ):
            clean.append({"op": "navigate", "path": path})
            visited = True
            project_opened = path.startswith("/projects/")
        elif op == "open_project" and action.get("slug") in slugs:
            clean.append({"op": "open_project", "slug": action["slug"]})
            visited = project_opened = True
        elif op == "focus" and isinstance(target, str) and (
            target in GUIDE_TARGETS or target in PROJECT_SECTIONS
            or (target.startswith("project-") and target[8:] in slugs)
        ):
            if target in PROJECT_SECTIONS and not project_opened:
                continue
            clean.append({"op": "focus", "target": target})
        elif op == "set_theme" and (action.get("mode") or action.get("theme")) in THEME_MODES:
            clean.append({"op": "set_theme", "mode": action.get("mode") or action.get("theme")})
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
