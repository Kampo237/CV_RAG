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
2b. Fin de conversation (« merci », « c'est bon ») → au revoir fixe   — sans LLM, sans question
2c. Chemin rapide ─── match ───▶ 1 appel Haiku en streaming (ou texte fixe) ─▶ fin
        │ pas de match / message à Jordan en cours
        ▼
2d. Reformulation (LLM seulement si la question dépend de l'historique ; sautée pendant
    un message à Jordan ; clarification ignorée si le visiteur répond à une question)
    puis seconde chance du chemin rapide sur la question reformulée
3.  Agent ReAct (RAG_MODE=agent) ou graphe LangGraph (automate), en streaming
4.  Ligne [[guide]] : construite par le code à partir des outils d'action de l'agent
    (ou interceptée et validée si le modèle l'écrit lui-même), émise en toute fin
5.  Historique : cache mémoire mis à jour, écriture Neon en arrière-plan
```

Le front envoie avec chaque question un `context` : `{"theme": "light"|"dark", "path": "/…"}`
(thème affiché, page courante). Le chat ne « bascule » plus un site déjà dans le thème demandé.

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

### Statut des formations

Même principe (`annotate_formations`) : `en cours`, `terminé — diplôme obtenu` ou
`terminé (sans diplôme)`, calculé depuis `en_cours` et `diplome_obtenu`. Le modèle ne
connaît pas la date du jour : sans ce statut, il présentait un DEC terminé comme « en cours ».
Le chemin rapide transmet aussi la date du jour dans le message.

### Dates

Les dates ne sont connues qu'au mois (1er du mois) ou à l'année (1er janvier) : ne pas y lire
un jour précis.

---

## 3. Chemin rapide — `app/Rag/fast_path.py`

Routeur par regex (aucun appel LLM, aucune reformulation), volontairement conservateur.

| Intention | Réponse | `[[guide]]` |
|---|---|---|
| Salutation (« Bonjour ») | texte fixe : prénom d'usage (Jordan) + titre du profil | — |
| Mode sombre / clair | texte fixe | `set_theme` (`mode: dark` / `light`) |
| CV / PDF | texte fixe avec `cv_pdf` ; vide → « je n'ai pas l'information » | `/cv` + `cv-download` (ou `cv-experience`) |
| Langues | texte fixe depuis les compétences de catégorie « Langues » | `/cv` + `cv-languages` si navigation |
| Certifications | texte fixe depuis les formations « Certified / PL-900 », avec statut | `/cv` + `cv-certifications` si navigation |
| Permis et distinctions | texte fixe (pas de table en base) + mentions trouvées dans les projets | `/cv` + `cv-distinctions` |
| « Parle-moi de toi » | Haiku sur le profil | `/about` + `about-intro` si navigation |
| Contact | texte fixe construit depuis le profil (email, téléphone, liens) | `/` + `home-contact` si navigation |
| À propos, façon de travailler, valeurs, centres d'intérêt | texte fixe (demande courte) | `/about` ou `/` + ancre |
| Liste / meilleurs projets | Haiku sur les projets actifs / mis en avant | `/projects` + `projects-grid` si navigation |
| Un projet nommé | Haiku sur la ligne du projet | `open_project` + `project-detail` si navigation |
| Section d'un projet (problème, approche, fonctionnalités, résultats, captures) | Haiku centré sur la section, sans extrapoler | `open_project` + `project-problem`… si navigation |
| Compétences, expériences, formation, témoignages | Haiku sur la table | section du site si navigation |

Une demande de navigation qui ajoute une vraie question (« emmène-moi aux centres d'intérêt
et parle-moi de ce qui te motive ») va à l'agent, qui répond et émet la ligne `[[guide]]`.

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
- **Outils d'action** : `set_site_theme(mode)`, `navigate_site(path, target)`,
  `open_project(slug, section)`. Le code valide chaque action (pages, sections, slugs actifs,
  une seule visite) et écrit lui-même la ligne `[[guide]]` : le modèle ne peut plus annoncer
  « je bascule en mode clair » sans que rien ne se passe. Thème déjà actif → l'outil le dit.
- **Message à Jordan** : voir ci-dessous. Les alertes autonomes (LEAD / PROJET / ALERTE)
  restent détectées par regex dans `main.py`.
- Streaming réel (`stream_mode="messages"`) ; `run_rag_agent` (non streamé) reste pour l'évaluation.

### Message à Jordan — `app/Rag/contact.py`

L'ancien protocole (130 lignes de prompt) laissait le modèle promettre un envoi sans outil,
exiger un courriel alors que le visiteur donnait un téléphone, ou être court-circuité par une
question de clarification. Les étapes sont désormais **imposées par le code** :

1. `prepare_contact_message(name, contact, message)` : nom, **courriel ou téléphone**, message
   (8 à 500 caractères) ; liens, publicité et tentatives d'injection refusés ; brouillon gardé
   pour la session (30 min). Un brouillon identique re-préparé garde sa date.
2. L'agent montre le récapitulatif et demande une confirmation.
3. `send_contact_message()` n'envoie que si un brouillon existe, **préparé lors d'un tour
   précédent**, et si le dernier message du visiteur est une confirmation explicite
   (« oui », « je confirme »…, sans « non » / « annule »).
4. Limites : 2 envois par session, `DAILY_CONTACT_LIMIT` (20) par jour.

Livraison : outil `send_sms` du serveur MCP, connexion ouverte **seulement au moment de
l'envoi** (plus de handshake MCP à chaque question) ; repli sur Twilio en direct si le MCP
ne répond pas. Le destinataire est toujours `ALERT_PHONE_NUMBER`, ou à défaut `JORDAN_PHONE`.
L'agent n'annonce un envoi que si l'outil répond « ENVOYÉ » ; sinon il le dit honnêtement.

---

## 5. Guidage du site — `app/Rag/guide.py`

La réponse peut se terminer par une seule ligne :

```
[[guide]]{"actions":[{"op":"open_project","slug":"safety-hub"},{"op":"focus","target":"project-detail"}]}
```

Contrat du front (validateur du bundle) :

| Op | Valeur |
|---|---|
| `navigate` | `path` : `/`, `/about`, `/projects`, `/cv`, `/testimonials`, `/projects/{slug}` |
| `focus` | `target` : une ancre de `GUIDE_TARGETS`, une section de fiche, ou `project-<slug>` |
| `open_project` | `slug` d'un projet actif |
| `set_theme` | `mode` : `light` ou `dark` (clé **`mode`**) |

- Au plus **4 actions** (le front tronque au-delà), **une seule visite** (`navigate` ou `open_project`).
- Sections de fiche (`project-detail`, `-overview`, `-problem`, `-approach`, `-features`,
  `-results`, `-gallery`) seulement après `open_project` ou `navigate /projects/{slug}` : seules, le front les ignore.
- Slugs validés contre les **projets actifs en base** ; chemins avec `..` ou externes rejetés.
- Le prompt dit explicitement au modèle qu'il **peut** naviguer et changer le thème, et
  qu'émettre la ligne vaut exécution immédiate (pas de demande de confirmation).
- `GuideStreamFilter` intercepte la ligne dans le flux (même coupée entre deux chunks),
  la valide et la ré-émet à la fin. L'historique enregistre le texte visible, sans la ligne.
- Si le modèle n'écrit que la ligne `[[guide]]`, le texte visible devient « Voilà 👇 »
  (jamais de réponse vide ni de « rien trouvé »).

Le modèle se présente sous son prénom d'usage, **Jordan** (le site dit Jordan ; le nom
complet reste Yann Willy Jordan Pokam Teguia).

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
| `DAILY_CONTACT_LIMIT` | `20` | messages à Jordan transmis par jour, au maximum |
| `ALERT_PHONE_NUMBER` | `JORDAN_PHONE` | destinataire des messages (serveur MCP et repli Twilio) |

`DATABASE_URL` (tables canoniques) et `DB_*` (vecteurs, historique) doivent pointer vers la
**même** base Neon.

---

## 11. Déploiement

Avant chaque déploiement, le jeu d'évaluation (scénarios tirés des traces réelles) :

```bash
python -m app.evaluation.run_scenarios          # 37 contrôles déterministes, sans LLM
python -m app.evaluation.run_scenarios --live   # + scénarios de bout en bout (appels LLM)
```

Rien n'y est écrit en base et aucun SMS ne part (livraison remplacée par un enregistreur).
Les traces brutes exportées de LangSmith restent dans `dataset/`, ignoré par Git
(conversations de visiteurs, numéros de téléphone).

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
