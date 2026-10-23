# CV_RAG — l'assistant du portfolio de Jordan Pokam Teguia

API FastAPI qui fait tourner le chat de [portfolio.jordan-pokam.dev](https://portfolio.jordan-pokam.dev).
Le chat répond aux visiteurs sur le parcours, les projets et les compétences de Jordan à partir
d'une base Neon, les guide dans le site (navigation, thème clair / sombre) et peut transmettre
leur message à Jordan par SMS.

## Ce que fait le chat

- **Répond à partir de la base, pas de sa mémoire** : les faits viennent des tables canoniques
  Neon (profil, projets, expériences, formation, compétences, témoignages). Une donnée masquée
  en base n'apparaît ni dans le chat ni sur le site.
- **Répond vite** : les questions courantes (projets, CV, contact, compétences, poste actuel…)
  passent par un chemin rapide — routeur sans LLM, données en cache, un seul appel à
  Claude Haiku 4.5 en streaming. Premier mot en ≈ 0,5–1 s.
- **Raisonne quand il le faut** : les questions qualitatives vont à un agent ReAct
  (Claude Sonnet 5) qui dispose d'outils de lecture de la base et de recherche vectorielle.
- **Guide dans le site** : ouvre une page, une fiche projet ou une section, change le thème.
  Les actions sont validées par le code et envoyées au site dans une ligne `[[guide]]`.
- **Transmet un message à Jordan** : récapitulatif, confirmation du visiteur, puis SMS via un
  serveur MCP (Twilio). Les étapes sont imposées par le code, pas laissées au modèle.
- **Garde les coûts sous contrôle** : fins de conversation sans appel au modèle, budget
  quotidien d'appels, limites par IP et par session.

## Architecture

```
Site React (portfolio-v2)
   │  POST /chat/  { question, session_id, context: { theme, path } }
   ▼
API FastAPI (app/main.py)
   ├─ anti-abus, historique (cache mémoire + Neon)
   ├─ fin de conversation ─────────────────────► au revoir fixe (sans LLM)
   ├─ chemin rapide (app/Rag/fast_path.py) ────► Claude Haiku 4.5, ou texte fixe
   └─ agent ReAct (app/Rag/agent.py) ──────────► Claude Sonnet 5 + outils
         ├─ tables canoniques Neon (app/Rag/canonical.py)
         ├─ recherche vectorielle pgvector + Voyage AI (cache dérivé des tables)
         ├─ actions sur le site → ligne [[guide]] (app/Rag/guide.py)
         └─ message à Jordan (app/Rag/contact.py) ──► serveur MCP SMS ──► Twilio
   ▲
   │  réponse en streaming, puis éventuellement la ligne [[guide]]{"actions":[…]}
Site : affiche le texte, exécute les actions
```

## Pile technique

Python 3.11 · FastAPI · LangChain / LangGraph · Claude API (Haiku 4.5, Sonnet 5) ·
PostgreSQL Neon + pgvector · Voyage AI (embeddings, reranking) · MCP (FastMCP) · Twilio ·
Docker · LangSmith (traçage).

## Structure

```
app/
  main.py                  routes, pipeline /chat/, historique, anti-abus
  auth.py                  clé d'administration (Authorization: Bearer)
  Rag/
    fast_path.py           routeur sans LLM et réponses rapides
    agent.py               agent ReAct et ses outils
    canonical.py           lecture des tables canoniques Neon (SQL écrit à la main)
    contact.py             message à Jordan : validation, confirmation, livraison
    guide.py               actions du site et validation de la ligne [[guide]]
    generation.py          reformulation et génération (mode automate)
    graph.py, router.py, sql_chain.py   mode automate (graphe LangGraph)
    vector_store.py, retrieval.py       pgvector, reranking Voyage AI
  rebuild_knowledge_cache.py   régénère datas + embeddings depuis les tables
  evaluation/run_scenarios.py  jeu d'évaluation de non-régression
mcp_servers/sms_server/    serveur MCP qui envoie le SMS (outil send_sms)
docs/                      documentation détaillée
sql/                       script d'alignement initial des données
```

## Démarrer en local

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows ; sous Linux/macOS : source .venv/bin/activate
pip install -r requirements.txt
```

Créer un `.env` à la racine (voir les variables ci-dessous), puis :

```bash
uvicorn app.main:app --port 8001 --reload        # API sur http://127.0.0.1:8001 (doc : /docs)
python -m mcp_servers.sms_server.server          # serveur MCP SMS sur le port 8010
```

En local, pointer l'API vers le serveur MCP avec `MCP_SMS_URL=http://localhost:8010/sse`
(la valeur `http://mcp-sms:8010/sse` ne fonctionne que dans le réseau Docker).

## Variables d'environnement

| Variable | Rôle |
|---|---|
| `ANTHROPIC_API_KEY` | Claude (obligatoire) |
| `VOYAGE_API_KEY` | embeddings et reranking (obligatoire) |
| `DATABASE_URL` | base Neon pour les tables canoniques |
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | même base Neon (vecteurs, historique) |
| `RAG_MODE` | `agent` (production) ou `automate` (graphe LangGraph, valeur par défaut) |
| `ADMIN_API_KEY` | protège les routes d'administration (sans elle : 503) |
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER` | envoi des SMS |
| `JORDAN_PHONE` | destinataire des SMS (alertes et messages de visiteurs) |
| `ALERT_PHONE_NUMBER` | destinataire des messages, si différent de `JORDAN_PHONE` |
| `MCP_SMS_URL` | adresse du serveur MCP (`http://mcp-sms:8010/sse` en Docker) |

Optionnelles : `AGENT_EFFORT` (`low`), `CANONICAL_CACHE_TTL` (300 s), `HISTORY_CACHE_TTL` /
`HISTORY_CACHE_MAX`, `DAILY_LLM_BUDGET`, `DAILY_CONTACT_LIMIT`, `MAX_REQUESTS_PER_SESSION`,
`MAX_QUESTION_CHARS`, `IP_WINDOW_SECONDS` / `IP_MAX_IN_WINDOW`, `ALERT_COOLDOWN_SEC`,
`ENVIRONMENT`, `LANGSMITH_*` (traçage). `OPENAI_API_KEY` ne sert qu'à l'évaluation RAGAS
(`app/evaluation/run_baseline.py`).

## Docker

```bash
docker compose up -d        # services api (port 8001) et mcp-sms (réseau interne seulement)
```

Le serveur MCP n'est pas exposé sur l'hôte : seul le service `api` peut l'appeler.

## Données : Neon source de vérité

Les faits s'écrivent dans les tables `portfolio_app_*` et `testimonials`. La table `datas` et
les embeddings ne sont qu'un cache, à régénérer après chaque modification :

```bash
python -m app.rebuild_knowledge_cache           # aperçu
python -m app.rebuild_knowledge_cache --apply   # régénère datas + embeddings
python -m app.rebuild_knowledge_cache --check   # contrôles de cohérence
```

## Évaluation

Scénarios tirés de vraies conversations (anonymisées), à lancer avant chaque déploiement :

```bash
python -m app.evaluation.run_scenarios          # contrôles déterministes, sans LLM
python -m app.evaluation.run_scenarios --live   # + scénarios de bout en bout (appels LLM)
```

Rien n'est écrit en base et aucun SMS ne part. `tests/test_corrections.py` couvre
l'authentification des routes (pytest, à installer à part).

## API

| Route | Accès | Rôle |
|---|---|---|
| `POST /chat/` | public | question du visiteur, réponse en streaming |
| `GET /portfolio/profile`, `/projects`, `/projects/{slug}`, `/experiences`, `/education`, `/skills` | public | données lues par le site |
| `GET /comments/`, `POST /comments/` | public | témoignages approuvés, dépôt d'un témoignage |
| `DELETE /history/{session_id}` | public | effacer sa conversation (bouton du chat) |
| `GET /stats/`, `/logs/`, `/history/{session_id}`, `/comments/?approved_only=false` | clé admin | administration |
| `POST /knowledge/add`, `PATCH`/`DELETE /comments/{id}`, `DELETE /clear/{category}` | clé admin | administration |

Clé d'administration : en-tête `Authorization: Bearer <ADMIN_API_KEY>` (bouton « Authorize »
dans `/docs`).

## Déploiement

```bash
docker build -t kpo237/cv-chatbot-api:latest -t kpo237/cv-chatbot-mcp-sms:latest .
docker push kpo237/cv-chatbot-api:latest
docker push kpo237/cv-chatbot-mcp-sms:latest

# sur l'instance
docker compose pull && docker compose up -d
```

## Documentation

- [docs/CHATBOT_NEON_SOURCE_DE_VERITE.md](docs/CHATBOT_NEON_SOURCE_DE_VERITE.md) — fonctionnement détaillé
- [BACKEND_NEON_SOURCE_DE_VERITE.md](BACKEND_NEON_SOURCE_DE_VERITE.md) — règles de données et de réponse
- [GUIDE_BACKEND_PROMPT.md](GUIDE_BACKEND_PROMPT.md) — contrat de la ligne `[[guide]]` avec le site
- [RAPPORT_CORRECTIFS.md](RAPPORT_CORRECTIFS.md) — autorisation des routes et vérification

L'ancien portfolio Django (janvier 2026) est archivé sous le tag `archive/django-portfolio`.
