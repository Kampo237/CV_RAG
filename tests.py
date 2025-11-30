"""
Diagnostic complet (version PRO)
Teste :
- Variables d'environnement
- Anthropic
- LangSmith
- Embeddings VoyageAI
- PGVector async (via ton VectorStoreService)
"""

import os
import asyncio
from dotenv import load_dotenv
from rich import print
from rich.panel import Panel
from rich.table import Table
from rich.console import Console

load_dotenv()
console = Console()


# =============================================================================
# 1. Vérification ENV
# =============================================================================
def test_env_variables():
    console.print(Panel("[bold cyan]Vérification des variables d'environnement[/bold cyan]", expand=False))

    checks = {
        "ANTHROPIC_API_KEY": "sk-ant-",
        "VOYAGE_API_KEY": "pa-",
        "LANGCHAIN_API_KEY": "lsv2_",
        "LANGCHAIN_TRACING_V2": "true",
        "LANGCHAIN_PROJECT": None,
        "LANGCHAIN_WORKSPACE": None,
        "DB_USER": None,
        "DB_PASSWORD": None,
        "DB_HOST": None,
        "DB_PORT": None,
        "DB_NAME": None,
    }

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Variable")
    table.add_column("Valeur")
    table.add_column("Statut")

    all_ok = True

    for var, prefix in checks.items():
        val = os.getenv(var, "")
        if not val:
            table.add_row(var, "[red]—[/red]", "[bold red]❌ Manquante[/bold red]")
            all_ok = False
            continue

        if prefix and not val.startswith(prefix):
            table.add_row(var, val, "[yellow]⚠️ Format inhabituel[/yellow]")
        else:
            display = f"{val[:12]}..." if "KEY" in var else val
            table.add_row(var, display, "[green]✔ OK[/green]")

    console.print(table)

    return all_ok


# =============================================================================
# 2. Test Anthropic
# =============================================================================
def test_anthropic():
    console.print(Panel("[bold cyan]Test Anthropic[/bold cyan]", expand=False))

    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

        models = [
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022",
            "claude-3-haiku-20240307",
        ]

        for model in models:
            console.print(f"→ Test du modèle [bold]{model}[/bold]...", end=" ")

            try:
                res = client.messages.create(
                    model=model,
                    max_tokens=5,
                    messages=[{"role": "user", "content": "ping"}]
                )
                print("[green]✔ OK[/green]")
                return True

            except Exception as e:
                if "not_found" in str(e):
                    print("[yellow]⚠️ Non disponible[/yellow]")
                else:
                    print(f"[red]❌ Erreur: {e}[/red]")

        console.print("[bold red]❌ Aucun modèle Anthropic fonctionnel[/bold red]")
        return False

    except Exception as e:
        console.print(f"[bold red]❌ Erreur Anthropic: {e}[/bold red]")
        return False


# =============================================================================
# 3. TEST PGVECTOR ASYNC via ton VectorStoreService
# =============================================================================
async def test_pgvector_async():
    console.print(Panel("[bold cyan]Test LangSmith + PGVector (async)[/bold cyan]", expand=False))

    try:
        from langsmith import Client
        from app.Rag.vector_store import VectorStoreService, EmbeddingRequest

        # ---- LangSmith ----
        client = Client(api_key=os.getenv("LANGCHAIN_API_KEY"))
        projects = list(client.list_projects(limit=1))

        console.print(f"[green]✔ Connexion LangSmith OK[/green]  (Projets: {len(projects)})")

        # ---- Vector Store ----
        service = VectorStoreService.get_instance()
        store = service.get_vector_store()

        console.print("[green]✔ Initialisation PGVector async OK[/green]")

        # ---- Test insertion ----
        test_req = [
            EmbeddingRequest(
                message_text="Ceci est un test de stockage vectoriel.",
                category="test"
            )
        ]

        res = await service.save_infos(test_req)

        console.print(f"[green]✔ Ajout document PGVector: {res}[/green]")

        # ---- Test recherche ----
        search_res = await service.search(
            request=type("Tmp", (object,), {
                "query": "test",
                "top_k": 3,
                "category_filter": None,
                "metadata_filter": None
            })()
        )

        console.print(f"[green]✔ Recherche OK[/green]")

        table = Table(title="Résultats recherche PGVector", show_lines=True)
        table.add_column("Score")
        table.add_column("Category")
        table.add_column("Texte")

        for r in search_res:
            table.add_row(str(r.similarity_score), r.category, r.content[:50] + "...")

        console.print(table)

        return True

    except Exception as e:
        console.print(f"[bold red]❌ Erreur PGVector: {e}[/bold red]")
        return False


# =============================================================================
# MAIN
# =============================================================================
async def main():
    console.print(Panel("[bold yellow]DIAGNOSTIC COMPLET - VERSION PRO[/bold yellow]", expand=False))

    # 1. ENV
    ok_env = test_env_variables()
    if not ok_env:
        console.print("[bold red]Corrige les variables d'environnement avant de continuer.[/bold red]")
        return

    # 2. Anthropic
    test_anthropic()

    # 3. PGVector async
    await test_pgvector_async()

    console.print(Panel("[bold green]DIAGNOSTIC TERMINÉ[/bold green]", expand=False))


if __name__ == "__main__":
    asyncio.run(main())
