"""
Tables canoniques Neon — seule source de vérité (cf. BACKEND_NEON_SOURCE_DE_VERITE.md)

Le site, le chatbot et le guide lisent les mêmes lignes :
  - portfolio_app_infopersonnelle (une ligne : identité, contact, cv_pdf)
  - portfolio_app_projet          (est_actif = true seulement)
  - portfolio_app_experience / _formation / _competence
  - testimonials                  (is_approved = true seulement)

Toutes les requêtes sont écrites ici, à la main (aucun SELECT généré par un
LLM). Les colonnes des tables Django hors projets/témoignages sont lues une
fois dans information_schema : le module s'adapte au schéma réel, filtre sur
est_actif et trie par ordre_affichage / ordre quand ces colonnes existent.

Cache mémoire de CACHE_TTL_SECONDS par table, rechargé paresseusement (pas de
rafraîchissement périodique : Neon doit pouvoir suspendre son compute). En cas
d'erreur DB, la dernière version connue est servie.

`datas`, `langchain_pg_embedding` et `faq` ne sont PAS lus ici : `datas` et
les embeddings sont un cache régénéré depuis ces tables
(app/rebuild_knowledge_cache.py), `faq` n'est pas une source de faits.
"""
import os
import re
import json
import time
import asyncio
import logging
import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from app.Rag.sql_chain import DB_URL

logger = logging.getLogger("rag_pipeline")

CACHE_TTL_SECONDS = int(os.getenv("CANONICAL_CACHE_TTL", "300"))

TABLES = {
    "profile": "portfolio_app_infopersonnelle",
    "projects": "portfolio_app_projet",
    "experiences": "portfolio_app_experience",
    "education": "portfolio_app_formation",
    "skills": "portfolio_app_competence",
    "testimonials": "testimonials",
}

# Colonnes jamais exposées (ni au chat, ni à l'API publique). Le téléphone
# en fait partie : le numéro de Jordan ne sort jamais (cf. protocole SMS).
_HIDDEN_COLUMN = re.compile(
    r"password|mot_de_passe|passwd|token|secret|hash|api_?key|telephone|phone|"
    r"^author_email$|^created_at$|^updated_at$"
)

_PROJECTS_SQL = text("""
    SELECT id, titre, slug, description_courte, description, contexte,
           fonctionnalites, resultats, technologies,
           url_github, url_demo, date_realisation, est_mis_en_avant, ordre
    FROM portfolio_app_projet
    WHERE est_actif = TRUE
    ORDER BY ordre, date_realisation DESC
""")

_TESTIMONIALS_SQL = text("""
    SELECT id, author_name, author_company, author_position, content, rating, is_featured
    FROM testimonials
    WHERE is_approved = TRUE
    ORDER BY is_featured DESC, created_at DESC
    LIMIT 20
""")

# NullPool : pas de connexion gardée ouverte (Neon peut suspendre son compute)
_engine = create_engine(DB_URL, poolclass=NullPool, pool_pre_ping=True,
                        connect_args={"connect_timeout": 5})
_cache: dict[str, tuple[float, list[dict]]] = {}
_locks: dict[str, asyncio.Lock] = {}
_columns: dict[str, list[str]] = {}


# =============================================================================
# LECTURE SQL (synchrone, appelée dans un thread)
# =============================================================================

def _table_columns(conn, table: str) -> list[str]:
    if table not in _columns:
        rows = conn.execute(
            text("SELECT column_name FROM information_schema.columns "
                 "WHERE table_schema = 'public' AND table_name = :t ORDER BY ordinal_position"),
            {"t": table},
        )
        _columns[table] = [r[0] for r in rows]
    return _columns[table]


def _generic_sql(table: str, columns: list[str], limit: Optional[int] = None):
    # Le nom de table vient de TABLES (constante), jamais de l'utilisateur.
    where = " WHERE est_actif = TRUE" if "est_actif" in columns else ""
    # Les modèles Django utilisent ordre_affichage (projets : ordre)
    order_col = next((c for c in ("ordre_affichage", "ordre", "id") if c in columns), None)
    order = f" ORDER BY {order_col}" if order_col else ""
    lim = f" LIMIT {int(limit)}" if limit else ""
    return text(f'SELECT * FROM "{table}"{where}{order}{lim}')


# Colonnes TEXT qui contiennent du JSON (modèle Django : TextField, pas JSONField)
_JSON_TEXT_COLUMNS = ("technologies", "fonctionnalites", "resultats", "realisations")


def _decode_json_text(row: dict) -> dict:
    for col in _JSON_TEXT_COLUMNS:
        value = row.get(col)
        if isinstance(value, str) and value.strip()[:1] in ("[", "{"):
            try:
                row[col] = json.loads(value)
            except ValueError:
                pass
    return row


def fetch_sync(kind: str) -> list[dict]:
    """Lit une table canonique (lignes publiques uniquement). Synchrone."""
    return [_decode_json_text(r) for r in _fetch_rows(kind)]


def _fetch_rows(kind: str) -> list[dict]:
    table = TABLES[kind]
    with _engine.connect() as conn:
        if kind == "projects":
            result = conn.execute(_PROJECTS_SQL)
        elif kind == "testimonials":
            result = conn.execute(_TESTIMONIALS_SQL)
        else:
            columns = _table_columns(conn, table)
            if not columns:
                logger.warning(f"[canonical] table {table} introuvable")
                return []
            result = conn.execute(_generic_sql(table, columns, limit=1 if kind == "profile" else None))
        return [dict(r._mapping) for r in result]


# =============================================================================
# CACHE
# =============================================================================

async def fetch(kind: str) -> list[dict]:
    """Lignes canoniques de `kind`, en cache. Lève si la DB est injoignable et le cache vide."""
    now = time.time()
    hit = _cache.get(kind)
    if hit and now - hit[0] < CACHE_TTL_SECONDS:
        return hit[1]

    lock = _locks.setdefault(kind, asyncio.Lock())
    async with lock:
        hit = _cache.get(kind)
        if hit and time.time() - hit[0] < CACHE_TTL_SECONDS:
            return hit[1]
        try:
            rows = await asyncio.to_thread(fetch_sync, kind)
            _cache[kind] = (time.time(), rows)
            logger.info(f"[canonical] {kind}: {len(rows)} lignes rechargées")
            return rows
        except Exception as e:
            logger.error(f"[canonical] lecture {kind} échouée: {e}")
            if hit:
                return hit[1]
            raise


async def fetch_or_empty(kind: str) -> list[dict]:
    try:
        return await fetch(kind)
    except Exception:
        return []


def invalidate(kind: Optional[str] = None) -> None:
    if kind:
        _cache.pop(kind, None)
    else:
        _cache.clear()


# =============================================================================
# ACCÈS MÉTIER
# =============================================================================

async def get_profile() -> dict:
    rows = await fetch_or_empty("profile")
    return rows[0] if rows else {}


async def get_cv_pdf() -> str:
    """Chemin public du PDF (colonne cv_pdf), ou "" si inconnu."""
    return str((await get_profile()).get("cv_pdf") or "").strip()


async def get_active_slugs() -> set[str]:
    """Slugs réels des projets actifs = segments /projects/:slug du site."""
    return {r["slug"] for r in await fetch_or_empty("projects") if r.get("slug")}


STATUS_MAIN = "⭐ poste principal actuel"
STATUS_PART_TIME = "emploi secondaire en cours (temps partiel)"
STATUS_ON_CALL = "sur appel seulement (pas un emploi régulier : j'y vais selon mes disponibilités et je peux refuser)"
STATUS_OTHER = "autre poste en cours"
STATUS_DONE = "terminé"


def _kind(row: dict) -> str:
    return re.sub(r"[^a-z ]", "", (row.get("type_experience") or "").lower()
                  .replace("é", "e").replace("è", "e"))


def _is_main(row: dict, rows: list[dict]) -> bool:
    """
    ⭐ Poste principal. Plusieurs expériences peuvent être en_cours en même
    temps : le type ne suffit pas (le poste principal peut être à temps partiel).
      - si la colonne est_principal existe (ajout Django futur) : elle fait foi ;
      - sinon, convention : l'expérience en cours, hors « sur appel », qui a le
        plus petit ordre_affichage (1 = ⭐).
    """
    if "est_principal" in row:
        return bool(row["est_principal"])
    candidates = [r for r in rows if r.get("en_cours") and "sur appel" not in _kind(r)]
    if not candidates:
        return False
    best = min(candidates, key=lambda r: (r.get("ordre_affichage") is None, r.get("ordre_affichage") or 0))
    return best is row


def experience_status(row: dict, rows: list[dict]) -> str:
    """Statut calculé par le code, pas deviné par le modèle."""
    if not row.get("en_cours"):
        return STATUS_DONE
    if _is_main(row, rows):
        kind = (row.get("type_experience") or "").strip()
        return f"{STATUS_MAIN} ({kind.lower()})" if kind else STATUS_MAIN
    kind = _kind(row)
    if "sur appel" in kind:
        return STATUS_ON_CALL
    if "partiel" in kind:
        return STATUS_PART_TIME
    return STATUS_OTHER


def is_main_status(status: str) -> bool:
    return status.startswith(STATUS_MAIN)


def annotate_experiences(rows: list[dict]) -> list[dict]:
    """Copies des lignes avec un champ `statut` (lecture LLM uniquement, pas l'API)."""
    return [{**r, "statut": experience_status(r, rows)} for r in rows]


async def get_project(slug: str) -> Optional[dict]:
    for row in await fetch_or_empty("projects"):
        if row.get("slug") == slug:
            return row
    return None


# =============================================================================
# SÉRIALISATION
# =============================================================================

def _jsonable(value):
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def public_row(row: dict) -> dict:
    """Ligne sans colonnes cachées, valeurs sérialisables en JSON."""
    return {k: _jsonable(v) for k, v in row.items() if not _HIDDEN_COLUMN.search(k)}


def _as_text(value) -> str:
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    if isinstance(value, dict):
        return ", ".join(f"{k}: {v}" for k, v in value.items())
    return str(_jsonable(value))


def format_rows(rows: list[dict], skip: tuple = ("id",)) -> str:
    """Texte lisible par le LLM : une ligne canonique = un bloc `colonne : valeur`."""
    blocks = []
    for row in rows:
        lines = [f"{k} : {_as_text(v)}" for k, v in public_row(row).items()
                 if k not in skip and v not in (None, "", [], {})]
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def format_project_line(row: dict) -> str:
    date = row.get("date_realisation")
    year = f" ({date.year})" if hasattr(date, "year") else ""
    star = " [mis en avant]" if row.get("est_mis_en_avant") else ""
    return (f"- {row.get('titre')} (slug: {row.get('slug')}){year}{star} — "
            f"{row.get('description_courte') or ''} | technos : {_as_text(row.get('technologies') or [])}")
