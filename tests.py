import os
import asyncio
from dotenv import load_dotenv
from rich import print
from rich.panel import Panel
from rich.table import Table
from rich.console import Console
import psycopg2
load_dotenv()
console = Console()

# =============================================================================
# MYSQL TEST
# =============================================================================
def test_mysql():
    console.print(Panel("[bold cyan]Test MySQL[/bold cyan]", expand=False))

    try:
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            database=os.getenv("DB_NAME"),
        )

        cursor = conn.cursor()

        # ---- tables ----
        cursor.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema='public'
        """)

        tables = cursor.fetchall()

        console.print("\n[bold green]✔ Tables trouvées :[/bold green]")
        for t in tables:
            console.print("-", t[0])

        # ---- structure ----
        if tables:
            table_name = "testimonials"
            console.print(f"\n[bold]Structure exemple : {table_name}[/bold]")

            cursor.execute(f"""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name='{table_name}'
            """)
            cols = cursor.fetchall()

            console.print(cols)

        cursor.close()
        conn.close()
        console.print("[green]✔ MySQL OK[/green]")
        return True

    except Exception as e:
        console.print(f"[red]❌ MySQL erreur: {e}[/red]")
        return False


# =============================================================================
# MAIN
# =============================================================================
async def main():
    console.print(Panel("[bold yellow]DIAGNOSTIC COMPLET[/bold yellow]", expand=False))

    test_mysql()

    console.print(Panel("[bold green]FIN[/bold green]", expand=False))


if __name__ == "__main__":
    asyncio.run(main())