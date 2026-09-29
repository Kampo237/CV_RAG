"""Contrôles des correctifs : auth des routes, refus de `datas`, ordre des tables."""
import os

os.environ["ADMIN_API_KEY"] = "cle-de-test"

from fastapi.testclient import TestClient

from app.Rag.graph import _table_order
from app.Rag.sql_chain import canonical_sql_or_error
from app.main import app

client = TestClient(app)
AUTH = {"Authorization": "Bearer cle-de-test"}


def test_sql_guard():
    assert canonical_sql_or_error("SELECT * FROM datas") .startswith("ERREUR")
    assert canonical_sql_or_error("DELETE FROM portfolio_app_projet") .startswith("ERREUR")
    assert canonical_sql_or_error("SELECT titre FROM portfolio_app_projet WHERE est_actif") is None


def test_table_order_skips_datas():
    order = _table_order("où as-tu travaillé")
    assert "datas" not in order
    assert order[0] == "portfolio_app_experience"


def test_public_portfolio_stays_open():
    response = client.get("/portfolio/projects")
    assert response.status_code == 200
    slugs = [row["slug"] for row in response.json()]
    assert "safety-hub" in slugs
    assert "nova-games" not in " ".join(slugs)
    assert client.get("/comments/?approved_only=true").status_code == 200


def test_admin_routes_reject_anonymous():
    assert client.get("/stats/").status_code == 401
    assert client.get("/logs/").status_code == 401
    assert client.get("/history/session-inconnue").status_code == 401
    assert client.get("/comments/?approved_only=false").status_code == 401
    assert client.post("/knowledge/add", json=[]).status_code == 401
    assert client.delete("/clear/projet").status_code == 401


def test_admin_routes_accept_the_key():
    stats = client.get("/stats/", headers=AUTH)
    assert stats.status_code == 200
    assert "datas" in stats.json()
    hidden = client.get("/comments/?approved_only=false", headers=AUTH)
    assert hidden.status_code == 200


def test_chat_can_still_forget_its_session():
    response = client.delete("/history/session-de-test-sans-ligne")
    assert response.status_code == 200


if __name__ == "__main__":
    test_sql_guard()
    test_table_order_skips_datas()
    test_public_portfolio_stays_open()
    test_admin_routes_reject_anonymous()
    test_admin_routes_accept_the_key()
    test_chat_can_still_forget_its_session()
    print("CORRECTIONS_OK")
