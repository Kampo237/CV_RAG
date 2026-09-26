# Chatbot du portfolio — Neon comme source de vérité

Ce document décrit le fonctionnement du backend après la refonte de septembre 2026 :
réponses rapides, lecture des tables canoniques Neon, guidage du site (`[[guide]]`)
et reconstruction du cache vectoriel.

Documents de référence (exigences) :
- [`BACKEND_NEON_SOURCE_DE_VERITE.md`](../BACKEND_NEON_SOURCE_DE_VERITE.md) — règles de données et de réponse
- [`GUIDE_BACKEND_PROMPT.md`](../GUIDE_BACKEND_PROMPT.md) — format de la ligne `[[guide]]` attendue par le front

---

## 1. Parcours d'une question (`POST /chat/`)

```
1.  Rate limiting + anti-abus (IP, longueur, budget quotidien)         — sans LLM
2.  Historique  ∥  routeur du chemin rapide (en parallèle)             — sans LLM
2a. Alertes SMS autonomes (LEAD / PROJET / ALERTE, par regex)          — sans LLM
2b. Chemin rapide ─── match ───▶ 1 appel Haiku en streaming (ou texte fixe) ─▶ fin
        │ pas de match / table canonique vide
        ▼
2c. Reformulation (LLM seulement si la question dépend de l'historique)
3.  Agent ReAct (RAG_MODE=agent) ou graphe LangGraph (automate), en streaming
4.  Filtre [[guide]] : la ligne est retenue, validée, puis émise en toute fin
5.  Historique : cache mémoire mis à jour, écriture Neon en arrière-plan
```

Latence mesurée (caches chauds) : le backend ajoute ~0 ms ; le premier token
dépend de Haiku (≈ 0,5–1 s). Chaque requête logue `⚡ premier token à Xms`.

---

## 2. Tables canoniques — `app/Rag/canonical.py`

Seul module qui lit les faits. SQL écrit à la main, jamais généré par un LLM.

| Clé | Table | Filtre |
|---|---|---|
| `profile` | `portfolio_app_infopersonnelle` | une ligne |
| `projects` | `portfolio_app_projet` | `est_actif = TRUE`, tri `ordre` |
| `experiences` | `portfolio_app_experience` | `est_actif`, tri `ordre_affichage` |
| `education` | `portfolio_app_formation` | `est_actif`, tri `ordre_affichage` |
| `skills` | `portfolio_app_competence` | `est_actif`, tri `ordre_affichage` |
| `testimonials` | `testimonials` | `is_approved = TRUE` |

- Cache mémoire par table (`CANONICAL_CACHE_TTL`, 300 s), rechargé à la demande — pas de
  rafraîchissement périodique pour laisser Neon suspendre son compute. En cas d'erreur DB,
  la dernière version connue est servie.
- Colonnes des tables Django lues dans `information_schema` : le code suit le schéma réel.
- `technologies`, `fonctionnalites`, `resultats` de `portfolio_app_projet` sont du **TEXT**
  contenant du JSON : décodés en listes à la lecture.
- Colonnes jamais exposées (API ni chat) : téléphone, mots de passe, jetons, `author_email`…
- `datas`, `langchain_pg_embedding` et `faq` ne sont **pas** des sources (voir §8).

### Statut des expériences (poste principal ⭐)

Plusieurs expériences peuvent être `en_cours` en même temps ; le type seul ne dit pas
laquelle est le poste principal. Le statut est donc **calculé par le code** (`annotate_experiences`)
et transmis au modèle :

| Statut | Règle |
|---|---|
| `⭐ poste principal actuel (<type>)` | colonne `est_principal` si elle existe ; sinon l'expérience en cours, hors « sur appel », au plus petit `ordre_affichage` |
| `emploi secondaire en cours (temps partiel)` | en cours, type contenant « partiel » |
| `sur appel seulement (…)` | en cours, type contenant « sur appel » |
| `terminé` | `en_cours = FALSE` |

**Convention actuelle : `ordre_affichage = 1` = poste principal.** Pour un vrai champ,
ajouter `est_principal = models.BooleanField(default=False)` au modèle Django + migration :
le code le lit automatiquement. Une expérience à masquer passe à `est_actif = FALSE`.

Pour « où travailles-tu ? » / « ton poste actuel », seul le poste ⭐ est transmis au modèle.

---

## 3. Chemin rapide — `app/Rag/fast_path.py`

Routeur par regex (aucun appel LLM, aucune reformulation), volontairement conservateur.

| Intention | Réponse | `[[guide]]` |
|---|---|---|
| CV / PDF | texte fixe avec `cv_pdf` ; vide → « je n'ai pas l'information » | `/cv` + `cv-download` (ou `cv-experience`) |
| Contact | texte fixe construit depuis le profil | `/` + `home-contact` si demande de navigation |
| À propos, façon de travailler | texte fixe | `/about` / `home-approach` |
| Liste des projets | Haiku sur les projets actifs | `/projects` + `projects-grid` si navigation |
| Un projet nommé | Haiku sur la ligne du projet | `open_project` + `project-detail` si navigation |
| Compétences, expériences, formation, témoignages | Haiku sur la table | section du site si navigation |

- Noms de projets reconnus depuis la base (titre, slug) + `EXTRA_ALIASES`.
- Questions qualitatives (« pourquoi », « comment », « meilleur », comparaison…), plusieurs
  projets nommés, demande de SMS → pipeline normal.
- Table canonique vide → pipeline normal (sauf demande de navigation : la page existe).
- **Les URL ne passent jamais par le LLM** (un modèle qui recopie une URL peut la corrompre) :
  contact en texte fixe, liens GitHub/démo ajoutés par le code quand le visiteur en demande.

---

## 4. Agent — `app/Rag/agent.py`

- Outils à SQL figé : `get_projects`, `get_profile`, `get_experiences` (avec statut),
  `get_education`, `get_skills`, `get_testimonials` ; plus `search_knowledge_base(query, category)`
  pour le qualitatif, filtré par catégorie avant le tri par similarité.
- Règles de source dans le prompt : faits uniquement issus des outils de la requête, lignes
  `get_*` prioritaires sur la recherche vectorielle, « Je n'ai pas cette information. » sinon.
- `claude-sonnet-5` réfléchit par défaut : `AGENT_EFFORT=low` (réglable) via `output_config.effort`.
- Prompt système mis en cache (`cache_control`) ; il ne change que si la liste des projets actifs change.
- **MCP SMS ouvert uniquement** si le visiteur demande à transmettre un message ou si le
  protocole SMS est en cours (`wants_sms`). Les alertes autonomes sont détectées par regex dans `main.py`.
- Streaming réel (`stream_mode="messages"`) ; `run_rag_agent` (non streamé) reste pour l'évaluation.

---

## 5. Guidage du site — `app/Rag/guide.py`

La réponse peut se terminer par une seule ligne :

```
[[guide]]{"actions":[{"op":"open_project","slug":"safety-hub"},{"op":"focus","target":"project-detail"}]}
```

- Routes et cibles fixes du site dans `GUIDE_PATHS` / `GUIDE_TARGETS`.
- Slugs (`open_project`, cartes `project-<slug>`) validés contre les **projets actifs en base**.
- `GuideStreamFilter` intercepte la ligne dans le flux (même coupée entre deux chunks),
  la valide (max 3 actions, `project-detail` seulement après `open_project`) et la ré-émet à la fin.
- L'historique enregistre le texte visible, sans la ligne `[[guide]]`.

---

## 6. Reformulation conditionnelle — `app/Rag/generation.py`

`needs_rephrase()` : l'appel LLM de reformulation n'a lieu que si la question dépend de
l'historique (pronoms de rappel, relances « et … », messages de 3 mots ou moins, qui gardent
la demande de clarification). Sinon la question est seulement nettoyée localement.

---

## 7. Historique — `app/main.py`

- Cache mémoire par session (`HISTORY_CACHE_TTL` 1800 s, `HISTORY_CACHE_MAX` 1000 sessions).
- Écriture Neon en arrière-plan sur un thread unique (ordre préservé, pas de mise à jour perdue).
- `DELETE /history/{session_id}` purge aussi le cache.
- Hypothèse : **un seul worker uvicorn** (comme le rate limiting). Avec plusieurs workers,
  passer ces états dans un stockage partagé.

---

## 8. Cache de connaissances — `app/rebuild_knowledge_cache.py`

`datas` et la collection `cv_knowledge_base` sont **régénérés** depuis les tables canoniques :
un fait par ligne, catégories `identite`, `contact`, `projet`, `experience`, `formation`,
`competence`, métadonnées `source_table` / `source_id` / `slug`, ids stables
(`table:id:catégorie`).

```bash
python -m app.rebuild_knowledge_cache           # aperçu, rien n'est écrit
python -m app.rebuild_knowledge_cache --apply   # vide puis régénère datas + embeddings
python -m app.rebuild_knowledge_cache --check   # contrôles §6 du document de référence
```

À lancer **après chaque modification des tables canoniques**. Garde-fous : refuse si aucune
ligne canonique, ou si le profil est vide (sauf `--force`). `faq`, `chat_sessions` et
`testimonials` ne sont jamais embeddés.

Conséquences côté API :
- `POST /knowledge/add` refuse les catégories hors liste.
- `POST /knowledge/ingest-document` renvoie **410** : ré-ingérer un document entier ajoute des
  voisins qui se recouvrent au lieu de remplacer les mauvais.

`sql/aligner_neon_source_de_verite.sql` garde la trace de l'alignement initial des données.

---

## 9. API publique en lecture seule

| Route | Contenu |
|---|---|
| `GET /portfolio/profile` | profil sans colonnes cachées |
| `GET /portfolio/projects` | projets actifs, tri `ordre` |
| `GET /portfolio/projects/{slug}` | un projet actif (404 sinon) |
| `GET /portfolio/experiences` · `/education` · `/skills` | tables correspondantes |
| `GET /comments/` | témoignages approuvés (déjà existant) |

---

## 10. Configuration

Aucune nouvelle variable obligatoire. Variables optionnelles :

| Variable | Défaut | Rôle |
|---|---|---|
| `AGENT_EFFORT` | `low` | effort de réflexion de l'agent (`low`→`max`) |
| `CANONICAL_CACHE_TTL` | `300` | durée du cache des tables canoniques (s) |
| `HISTORY_CACHE_TTL` / `HISTORY_CACHE_MAX` | `1800` / `1000` | cache d'historique |

`DATABASE_URL` (tables canoniques) et `DB_*` (vecteurs, historique) doivent pointer vers la
**même** base Neon.

---

## 11. Déploiement

```bash
docker build -t kpo237/cv-chatbot-api:latest -t kpo237/cv-chatbot-api:<AAAA-MM-JJ-sujet> .
docker push kpo237/cv-chatbot-api:<AAAA-MM-JJ-sujet>
docker push kpo237/cv-chatbot-api:latest

# sur l'instance
docker compose pull api && docker compose up -d api
```

L'image `cv-chatbot-mcp-sms` n'est à reconstruire que si `mcp_servers/` ou `requirements.txt` change.
Le tag daté permet un retour arrière (`image: kpo237/cv-chatbot-api:<tag>`).

---

## 12. Limites connues

- Le poste principal repose sur la convention `ordre_affichage = 1` tant que `est_principal`
  n'existe pas dans le modèle Django.
- `models.py` (projet Django) n'est pas dans ce dépôt : les `choices` éventuels de
  `type_experience` / `recherche_type` ne sont pas vérifiés ici.
- Les questions qualitatives passent par l'agent : premier token nettement plus lent que le chemin rapide.
- Routes d'administration sans authentification (`PATCH`/`DELETE /comments`, `DELETE /clear/{category}`,
  `GET /comments/?approved_only=false`) — à protéger.
