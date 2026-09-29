# Rapport des correctifs — 28 septembre 2026

Lecture du site `portfolio-v2` et de l’API `FastAPIProject`. Les tests ci-dessous ont été exécutés sur le code local et sur le serveur de développement. L’API publique `https://api.jordan-pokam.dev` ne porte ces changements d’autorisation qu’après redémarrage du processus FastAPI avec ce code.

## Phase 1 — Autorisation des routes sensibles

**Constat.** Six familles de routes répondaient sans identité : statistiques, journaux, lecture d’un historique de chat, ajout de connaissances, effacement d’une catégorie, approbation et suppression des témoignages, et la liste des témoignages non approuvés.

**Correctif.** `app/auth.py` exige l’en-tête `Authorization: Bearer <ADMIN_API_KEY>`. La valeur est lue dans l’environnement du serveur. Si la variable est absente, ces routes répondent 503 (fermées). Si le jeton est absent ou faux, 401. La comparaison est à temps constant.

**Pourquoi ce chemin.** Le navigateur du portfolio ne doit jamais recevoir cette clé. Le bouton « effacer la conversation » appelle `DELETE /history/{session}` sans secret : cette route reste publique, parce que l’identifiant de session est déjà le secret du visiteur. La lecture du même historique, elle, exige la clé.

**Routes protégées**

| Méthode | Chemin | Sans clé |
|---|---|---|
| GET | `/stats/` | 401 |
| GET | `/logs/` | 401 |
| GET | `/history/{session}` | 401 |
| GET | `/comments/?approved_only=false` | 401 |
| POST | `/knowledge/add` | 401 |
| POST | `/knowledge/ingest-document` | 401 |
| DELETE | `/clear/{category}` | 401 |
| PATCH | `/comments/{id}/status` | 401 |
| DELETE | `/comments/{id}` | 401 |

**Restent publics, à dessein**

- `POST /chat/`
- `GET /portfolio/projects`, `/portfolio/profile`, expériences, formation, compétences
- `GET /comments/` avec le défaut `approved_only=true`
- `POST /comments/` (dépôt d’un témoignage, toujours non approuvé)
- `DELETE /history/{session}` (le widget)

**Justificatif des stats.** `GET /stats/` plantait ensuite sur un modèle `Embeddings` qui n’existe pas. La route compte maintenant `datas` et `langchain_pg_embedding`, et n’écrit plus le détail de l’exception dans la réponse.

**Clé.** `ADMIN_API_KEY` a été ajoutée au `.env` local. Elle n’est pas recopiée ici. Il faut la même variable sur le serveur qui exécute l’API, puis redémarrer ce processus. Tant que ce n’est pas fait, l’API en ligne reste ouverte sur ces routes.

## Phase 2 — La grille lit Neon

**Constat.** Le site appelait `/api/projects` et `/projects`, qui répondent 404. L’API sert déjà `GET /portfolio/projects` (cinq projets, slugs du site).

**Correctif.** `src/hooks/useProjects.ts` n’appelle plus que `/portfolio/projects`. Les textes, technologies et liens viennent de cette réponse. Le fichier local ne complète que ce que la base ne porte pas : galerie, métriques, taille d’équipe, fourchette d’années. Si l’appel échoue, la liste locale reste affichée.

**Justification.** Une seule liste de projets, celle de `portfolio_app_projet`. Les 404 dans la console venaient de routes qui n’existent pas.

**Vérification.** Sur `http://127.0.0.1:5173/projects`, SafetyHub affiche la phrase de la base (« Système d'analyse des risques… ») et la carte CV Chatbot RAG affiche LangChain et LangGraph, absents du fichier local. L’appel direct depuis la page a renvoyé 200 et 5 lignes.

## Phase 3 — Le SQL ne lit plus `datas`

**Constat.** Le chemin lent générait des `SELECT` sur `datas`, un cache de morceaux de markdown. Une question qualitative pouvait donc citer d’anciens faits.

**Correctif.** Les tables autorisées sont `portfolio_app_projet`, `portfolio_app_experience`, `portfolio_app_formation`, `portfolio_app_competence`, `portfolio_app_infopersonnelle`. Un garde refuse toute requête qui contient le mot `datas` ou qui n’est pas un `SELECT`. Le graphe choisit d’abord la table qui correspond à la question (un emploi ouvre les expériences, pas les projets). Les prompts ne demandent plus de filtrer `datas.category`. La colonne `telephone` est exclue des schémas donnés au modèle.

**Justification.** Les faits sont les lignes canoniques. `datas` et les embeddings restent un cache, à reconstruire avec `python -m app.rebuild_knowledge_cache --apply` quand ce code sera celui qui tourne en production. Cette reconstruction n’a pas été lancée : elle efface le cache d’embeddings de la base en ligne.

**Vérification.** `canonical_sql_or_error("SELECT * FROM datas")` est rejeté. Pour « où as-tu travaillé », la première table choisie est `portfolio_app_experience`.

## Phase 4 — Surlignage

**Constat.** Le contrat était déjà dans le site : couper `[[guide]]`, ouvrir la page, poser le voile et l’anneau, puis les retirer.

**Vérification, serveur local, API en ligne.**

1. Question « Montre-moi comment tu travailles » depuis la page projets.
2. Réponse en 272 ms : « Voici comment je travaille ». La bulle ne contient pas `[[guide]]`.
3. L’adresse est passée à `/`, sur la section Comment je travaille.
4. Un second appel du guide sur `home-approach` a renvoyé `ok: true` et a posé `guide-spotlight-veil` et `guide-spotlight-ring` dans la page.

## Résultats des contrôles automatiques

Script `tests/test_corrections.py`, client de test branché sur ce code et sur Neon. Sortie : `CORRECTIONS_OK`.

| Contrôle | Résultat |
|---|---|
| `GET /portfolio/projects` sans clé | 200, slug `safety-hub` présent |
| `GET /comments/?approved_only=true` | 200 |
| Stats, logs, historique, témoignages cachés, ajout de connaissances, effacement | 401 |
| `GET /stats/` avec la clé de test | 200 |
| Témoignages non approuvés avec la clé | 200 |
| `DELETE /history/…` sans clé | 200 |
| TypeScript du portfolio (`tsc -b --noEmit`) | 0 erreur |
| Compilation Python des modules touchés | succès |

## Ce qui reste hors de cette machine

- Redémarrer l’API en production avec ce code et `ADMIN_API_KEY`. Sans ça, les routes sensibles de `api.jordan-pokam.dev` sont encore ouvertes.
- Republier le `dist` du portfolio pour que `https://portfolio.jordan-pokam.dev` lise `/portfolio/projects`. Le serveur de développement le fait déjà.
- Reconstruire le cache `datas` / embeddings une fois l’API redéployée, pour que le chemin vectoriel ne garde pas d’anciens morceaux.

---

## Vérification du rapport — 29 septembre 2026

Chaque affirmation a été contrôlée sur le code et sur Neon avant commit.

| Point | Verdict | Preuve |
|---|---|---|
| Phase 1 — routes protégées (9), 503 sans clé serveur, 401 sinon, comparaison à temps constant | Fondé | `secrets.compare_digest` ; 401 sans clé ou clé fausse, 200 avec la clé ; `DELETE /history` reste public |
| Phase 1 — `/stats/` plantait sur `models.Embeddings` | Fondé | ce modèle n’existe pas dans `app/models.py` ; la route répond 200 avec la clé |
| Phase 2 — `/portfolio/projects` sert 5 projets, LangChain/LangGraph, phrase SafetyHub de la base | Fondé (côté API) | vérifié ; CORS ouvert. Le code du site n’est pas dans ce dépôt : non vérifiable ici |
| Phase 2 — site en ligne pas encore republié | Fondé | le bundle en ligne appelle encore `/api/projects`, jamais `/portfolio/projects` |
| Phase 3 — `datas` refusé, table choisie selon la question | Fondé | garde et `_table_order` testés. Portée : chemin `automate` (graphe) ; en mode `agent` (production), les outils lisaient déjà les tables canoniques |
| Phase 3 — « tables autorisées », « telephone exclu » | Partiel → corrigé | la garde ne refusait que `datas` et les non-SELECT. Elle refuse désormais toute table hors des tables canoniques (`chat_sessions`, `testimonials`, `faq`…), la colonne `telephone`, `SELECT *` sur le profil et les requêtes multiples |
| Phase 3 / « Reste à faire » — cache `datas` non reconstruit | **Obsolète** | le cache a déjà été régénéré depuis les tables canoniques (`rebuild_knowledge_cache --apply`) : 61 faits, catégories autorisées, `--check` OK. Le cache vit dans Neon : rien à relancer au redéploiement |
| Phase 4 — « Montre-moi comment tu travailles » | Fondé (côté API) | « Voici comment je travaille », ligne `[[guide]]` vers `home-approach` ; surlignage côté site non vérifiable ici |

Ajouts faits pendant la vérification :
- `app/auth.py` passe par `HTTPBearer` : le schéma `AdminKey` est déclaré dans l’OpenAPI, le bouton « Authorize » apparaît dans `/docs` (comportement 401 / 503 inchangé).
- Mot-clé d’une entreprise masquée retiré de `_table_order` (code public).
