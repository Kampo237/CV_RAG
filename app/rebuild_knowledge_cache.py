"""
Reconstruction du cache de connaissances depuis les tables canoniques Neon
(BACKEND_NEON_SOURCE_DE_VERITE.md §4, §6, §7)

`datas` et `langchain_pg_embedding` (collection cv_knowledge_base) ne sont
plus une source : ce sont des caches régénérés à partir de
portfolio_app_infopersonnelle / _projet / _experience / _formation / _competence.
Une entrée par fait, jamais un chapitre entier.

Usage (depuis la racine du projet, avec le .env pointant sur Neon) :
    python -m app.rebuild_knowledge_cache           # aperçu : faits générés, rien n'est écrit
    python -m app.rebuild_knowledge_cache --check   # contrôles SQL du §6
    python -m app.rebuild_knowledge_cache --apply   # efface puis régénère datas + embeddings

--apply est destructif pour le cache (pas pour les tables canoniques) :
toutes les lignes de `datas` et la collection d'embeddings sont supprimées
avant régénération. `faq`, `chat_sessions`, `testimonials` ne sont pas touchés
ni embeddés. Refuse de tourner si les tables canoniques ne donnent aucun fait,
ou si la ligne de profil manque (sauf --force).
"""
import re
import sys
import argparse

from dotenv import load_dotenv
from langchain_core.documents import Document
from sqlalchemy import text

load_dotenv()

from app.Rag import canonical  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import Datas  # noqa: E402

CATEGORIES = ("identite", "experience", "formation", "competence", "projet", "contact")
EXPECTED_SLUGS = {"super-cchic", "cv-chatbot-rag", "safety-hub", "wpf-manager", "ecrin-de-julias"}

# Colonnes de la ligne d'identité qui relèvent du chunk « contact »
_CONTACT_COLUMN = re.compile(r"mail|linkedin|github|lien|link|url|site|disponib|cv_pdf|contact")
# Colonnes techniques sans valeur pour la recherche (bruit dans les embeddings)
_SKIP = ("id", "ordre", "ordre_affichage", "est_actif", "est_mis_en_avant", "image", "photo", "icone")


# =============================================================================
# FAITS
# =============================================================================

def _fact(category: str, table: str, row: dict, body: str, **extra) -> dict:
    source_id = row.get("id")
    meta = {"source_table": table, "source_id": source_id, "category": category, **extra}
    return {
        "id": f"{table}:{source_id}:{category}",   # stable → ré-ingérer remplace, n'ajoute pas
        "category": category,
        "text": body,
        "metadata": meta,
    }


def _kv(row: dict) -> str:
    return canonical.format_rows([row], skip=_SKIP)


def build_facts() -> list[dict]:
    facts: list[dict] = []

    for row in canonical.fetch_sync("profile"):
        public = canonical.public_row(row)
        contact = {k: v for k, v in public.items() if _CONTACT_COLUMN.search(k)}
        identity = {k: v for k, v in public.items() if k not in contact}
        table = canonical.TABLES["profile"]
        if len(identity) > 1:
            facts.append(_fact("identite", table, row, _kv(identity)))
        if contact:
            facts.append(_fact("contact", table, row, _kv({"id": row.get("id"), **contact})))

    for row in canonical.fetch_sync("projects"):
        body = _kv({k: row.get(k) for k in ("titre", "slug", "description_courte", "description", "technologies")})
        facts.append(_fact("projet", canonical.TABLES["projects"], row, body, slug=row.get("slug")))

    for kind, category in (("experiences", "experience"), ("education", "formation"), ("skills", "competence")):
        rows = canonical.fetch_sync(kind)
        if kind == "experiences":
            rows = canonical.annotate_experiences(rows)   # statut : principal / temps partiel / sur appel
        for row in rows:
            facts.append(_fact(category, canonical.TABLES[kind], row, _kv(row)))

    return facts


# =============================================================================
# CONTRÔLES §6
# =============================================================================

def run_checks() -> bool:
    ok = True
    with canonical._engine.connect() as conn:
        slugs = [r[0] for r in conn.execute(text(
            "SELECT slug FROM portfolio_app_projet WHERE est_actif ORDER BY ordre"))]
        print(f"Projets actifs : {slugs}")
        missing, extra = EXPECTED_SLUGS - set(slugs), set(slugs) - EXPECTED_SLUGS
        if missing or extra:
            ok = False
            print(f"  ✗ manquants : {sorted(missing)} | en trop : {sorted(extra)}")
        else:
            print("  ✓ les cinq slugs du site, rien d'autre")

        pdf = [r[0] for r in conn.execute(text(
            "SELECT cv_pdf IS NOT NULL AND cv_pdf <> '' FROM portfolio_app_infopersonnelle"))]
        if pdf == [True]:
            print("  ✓ cv_pdf renseigné (une ligne de profil)")
        else:
            ok = False
            print(f"  ✗ cv_pdf : {pdf or 'aucune ligne dans portfolio_app_infopersonnelle'}")

        cats = list(conn.execute(text("SELECT category, COUNT(*) FROM datas GROUP BY category")))
        print(f"Catégories datas : {cats}")
        bad = [c for c, _ in cats if c not in CATEGORIES]
        if bad:
            ok = False
            print(f"  ✗ catégories hors liste : {bad}")
        else:
            print("  ✓ aucune catégorie hors liste")
    print("\nRÉSULTAT :", "OK — Neon peut servir de source de vérité" if ok else "À CORRIGER")
    return ok


# =============================================================================
# RECONSTRUCTION
# =============================================================================

def apply(facts: list[dict]) -> None:
    from app.Rag.vector_store import get_vector_store_service

    # 1. Vider le cache SQL
    db = SessionLocal()
    try:
        deleted = db.query(Datas).delete()
        db.commit()
        print(f"datas : {deleted} lignes supprimées")

        # 2. Vider la collection d'embeddings, puis la recréer
        store = get_vector_store_service().get_vector_store()
        store.delete_collection()
        store.create_collection()
        print("embeddings : collection cv_knowledge_base vidée")

        # 3. Régénérer : une ligne datas + un embedding par fait (id stable)
        store.add_documents(
            [Document(page_content=f["text"], metadata=f["metadata"]) for f in facts],
            ids=[f["id"] for f in facts],
        )
        db.add_all([Datas(corpus=f["text"], category=f["category"], extradatas=f["metadata"]) for f in facts])
        db.commit()
        print(f"{len(facts)} faits réécrits (datas + embeddings)")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="efface puis régénère datas + embeddings")
    parser.add_argument("--check", action="store_true", help="contrôles SQL du §6 uniquement")
    parser.add_argument("--force", action="store_true",
                        help="reconstruire même si le profil (identité/contact) est absent")
    args = parser.parse_args()

    if args.check:
        return 0 if run_checks() else 1

    facts = build_facts()
    by_cat: dict[str, int] = {}
    for f in facts:
        by_cat[f["category"]] = by_cat.get(f["category"], 0) + 1
        if not args.apply:
            print(f"--- [{f['category']}] {f['id']}\n{f['text']}\n")
    print(f"Faits générés : {len(facts)} {by_cat}")

    if not facts:
        print("✗ Aucun fait dans les tables canoniques — remplis-les avant de reconstruire le cache.")
        return 1
    if not args.apply:
        print("\nAperçu seulement. Relance avec --apply pour écrire.")
        return 0
    if not any(f["category"] in ("identite", "contact") for f in facts) and not args.force:
        # Sans ligne de profil, le cache régénéré perdrait l'identité et le
        # contact que les anciens chunks portent encore : on refuse.
        print("✗ portfolio_app_infopersonnelle est vide : remplis-la d'abord (ou --force).")
        return 1

    apply(facts)
    print("\nContrôles §6 :")
    run_checks()
    print("\nLe cache mémoire de l'API expire en 5 min (CANONICAL_CACHE_TTL) ; redémarre l'API pour un effet immédiat.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
