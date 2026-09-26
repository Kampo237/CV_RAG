# Règles backend — Neon comme seule source de vérité

À appliquer sur le projet Neon `Cvdb` (`wispy-truth-93720141`, base `neondb`, région `aws-us-east-2`).
Le portfolio ne doit plus avoir une copie parallèle des faits. Le site, le chatbot et le guide lisent les mêmes lignes.

État constaté le 25 septembre 2026, par lecture SQL (pas par le JWKS) :

| Table | Lignes | Rôle actuel |
| --- | --- | --- |
| `portfolio_app_projet` | 4, toutes `est_actif = true` | Super CChic, CV Chatbot RAG, NOVA GAMES S2J, Gestionnaire WebNet |
| `portfolio_app_infopersonnelle` | 0 | Prévue pour identité, contact, `cv_pdf` — vide |
| `portfolio_app_experience` | 0 | Vide |
| `portfolio_app_formation` | 0 | Vide |
| `portfolio_app_competence` | 0 | Vide |
| `datas` | 14 | Markdown empilé, catégories `profil`, `Profil`, `cv_a_jour`, `mise à jour Sept-26` |
| `langchain_pg_embedding` | 14 | Index vectoriel collé à ces dumps |
| `faq` | 10 | Questions figées, pas une source de faits |
| `testimonials` | 2 approuvés | Seule table déjà utilisable telle quelle |

Le site v2, lui, décrit cinq projets dont les slugs sont `super-cchic`, `cv-chatbot-rag`, `safety-hub`, `wpf-manager`, `ecrin-de-julias`, plus un PDF dans `/public`. Aucun de ces slugs n’existe dans `portfolio_app_projet`. SafetyHub et L’Écrin de Julia’s n’y sont pas. NOVA GAMES y est encore actif. C’est pour ça que le chat liste Nova Games et nie le PDF.

Le JWKS Neon Auth ne donne pas accès aux lignes. L’audit se fait avec la connexion Postgres (MCP Neon ou l’URL du rôle backend).

---

## 1. Qui est la source

Les tables canoniques, les seules qu’on édite à la main :

- `portfolio_app_infopersonnelle` — une seule ligne. Identité, email, liens, disponibilité, `cv_pdf`.
- `portfolio_app_projet` — un projet par ligne. `est_actif = false` retire le projet du site et du chat sans l’effacer.
- `portfolio_app_experience`
- `portfolio_app_formation`
- `portfolio_app_competence`
- `testimonials` — le chat et le site ne lisent que `is_approved = true`.

`datas` et `langchain_pg_embedding` sont un cache régénéré à partir de ces tables. On n’y colle plus de markdown, on n’y invente plus de catégorie (`Profil`, `cv_a_jour`, `mise à jour Sept-26`). `faq` n’est pas une source de faits.

Slug = route du site. La valeur de `portfolio_app_projet.slug` est exactement le segment `/projects/:slug`. Pas de suffixe `-system` ou `-ecommerce` si le site n’utilise pas ce segment.

Projets à avoir actifs une fois la base alignée sur le site actuel :

| slug | titre |
| --- | --- |
| `super-cchic` | Super CChic |
| `cv-chatbot-rag` | CV Chatbot RAG |
| `safety-hub` | SafetyHub |
| `wpf-manager` | Gestionnaire de projets |
| `ecrin-de-julias` | L’Écrin de Julia’s |

`nova-games-ecommerce` passe à `est_actif = false`. Tout projet absent du site public passe à `est_actif = false`.

`portfolio_app_infopersonnelle.cv_pdf` contient le chemin public du PDF (`/CV_Jordan_Pokam_Teguia.pdf` ou l’URL absolue du fichier servi par le site). Tant que cette colonne est vide, le modèle n’a pas le droit de dire qu’il n’existe pas de PDF : il dit qu’il n’a pas l’information.

---

## 2. Ce que le chatbot a le droit de dire

Chaque phrase factuelle vient d’une ligne canonique lue pendant la requête.

- Projet cité seulement si `est_actif = true`.
- Contact, téléphone, GitHub, LinkedIn, disponibilité : colonnes de `portfolio_app_infopersonnelle`, pas le texte d’un vieux chunk.
- CV PDF : colonne `cv_pdf`. S’il y a une valeur, la donner. Sinon, ne pas inventer un envoi par texto.
- Témoignage : `is_approved = true` seulement.
- Si la requête ne ramène rien : « Je n’ai pas cette information. » Pas de projet de remplacement, pas de promesse d’envoi.

Interdit : répondre depuis la mémoire du modèle, depuis `faq`, ou depuis un chunk `datas` plus récent en apparence qu’une ligne canonique. Les addenda « mise à jour Sept-26 » ne font plus foi.

Le guide de navigation n’est pas une liste de phrases. Quand la question demande de montrer ou d’ouvrir quelque chose qui existe en base, la réponse texte est suivie d’une seule ligne finale :

```
[[guide]]{"actions":[{"op":"open_project","slug":"<slug réel>"},{"op":"focus","target":"project-detail"}]}
```

`slug` est copié de `portfolio_app_projet.slug`. Ne pas l’inventer.

Correspondances stables, déjà codées côté site :

| Intention | Actions |
| --- | --- |
| Liste des projets | `navigate` `/projects` puis `focus` `projects-grid` |
| Un projet précis | `open_project` avec son slug puis `focus` `project-detail` |
| CV ou PDF | `navigate` `/cv` puis `focus` `cv-download` si `cv_pdf` est rempli, sinon `cv-experience` |
| Expérience | `navigate` `/cv` puis `focus` `cv-experience` |
| Formation | `navigate` `/cv` puis `focus` `cv-education` |
| Compétences | `navigate` `/about` puis `focus` `about-skills` |
| Contact | `navigate` `/` puis `focus` `home-contact` |
| Témoignages | `navigate` `/testimonials` puis `focus` `testimonials-list` |
| Façon de travailler | `navigate` `/` puis `focus` `home-approach` |

Pas de ligne `[[guide]]` pour une question purement conversationnelle. Maximum 3 actions. Jamais d’URL externe, de `mailto`, ni de soumission de formulaire.

Cette ligne ne part dans le flux texte que lorsque le front sait la retirer avant affichage. D’ici là, la préparer côté modèle sans l’émettre dans le corps visible, ou l’émettre sur un canal séparé.

---

## 3. Mode opératoire — premier token rapide

Le mode `agent` actuel attend toute la chaîne avant d’envoyer le premier mot, puis découpe la réponse avec une pause de 30 ms par mot. Ce n’est pas du streaming.

Pour une question de portfolio :

1. Pas de reformulation LLM si la question tient seule.
2. Pas de connexion MCP SMS, sauf demande explicite de transmettre un message.
3. Pas d’agent ReAct. Pas de second appel modèle pour inventer un `SELECT`.
4. Requêtes SQL déjà écrites, filtrées par `est_actif` ou `is_approved`.
5. Un seul appel modèle, en `astream`, qui reçoit les lignes SQL en contexte et écrit la réponse.
6. Les tokens partent au client dès qu’ils existent. Supprimer la boucle `split` + `sleep(0.03)`.

Cible : premier octet en moins d’une seconde sur une question du type « quels sont tes projets ».

Le MCP SMS ne s’ouvre que si le visiteur demande d’envoyer un message, et seulement après nom, email et texte confirmés. Le numéro du destinataire reste fixé côté serveur.

---

## 4. Reconstruction du cache

Après chaque changement canonique :

1. Écrire ou mettre à jour les tables de la section 1.
2. Reconstruire `datas` : une ligne par fait, `category` uniquement parmi `identite`, `experience`, `formation`, `competence`, `projet`, `contact`. `corpus` = texte dérivé de la ligne canonique. `extradatas` contient `source_table` et `source_id`.
3. Supprimer les anciennes lignes `datas` dont la catégorie n’est pas dans cette liste.
4. Ré-embedder uniquement ces nouvelles lignes dans `langchain_pg_embedding`.
5. Ne pas embedder `faq`, `chat_sessions`, `chat_messages`, ni `neon_auth`.

Tant que l’étape 2 n’est pas faite, le retrieval vectoriel continuera de citer Nova Games et BiblioNova même si `portfolio_app_projet` est corrigé.

---

## 5. API lue par le site

Le front arrête d’appeler des routes absentes (`/api/projects`, `/projects` sur l’API chatbot) tant qu’elles ne lisent pas Neon.

Routes à exposer, lecture seule, données publiques :

- `GET /portfolio/profile` — la ligne `portfolio_app_infopersonnelle` sans champ secret hors email, liens, `cv_pdf`, bio, disponibilité.
- `GET /portfolio/projects` — `est_actif = true`, ordre par `ordre`.
- `GET /portfolio/projects/{slug}` — un projet actif.
- `GET /portfolio/experiences`
- `GET /portfolio/education`
- `GET /portfolio/skills`
- `GET /comments/` — déjà utilisé pour les témoignages approuvés.

Le navigateur ne reçoit pas de chaîne de connexion Neon ni de JWT Data API. Seul le backend parle à Postgres.

---

## 6. Contrôle après mise à jour

Ces lectures doivent réussir avant de considérer la base comme source de vérité :

```sql
SELECT slug, titre FROM portfolio_app_projet WHERE est_actif ORDER BY ordre;
SELECT cv_pdf IS NOT NULL AND cv_pdf <> '' FROM portfolio_app_infopersonnelle;
SELECT category, COUNT(*) FROM datas GROUP BY category;
```

Attendu : les cinq slugs du site, un PDF non vide, et aucune catégorie hors liste. Une question « montre tes projets » ne cite que les lignes actives. Une question « as-tu un CV PDF » cite `cv_pdf`.

---

## 7. Comment corriger les données déjà présentes

Ne pas ré-ingérer un nouveau document unique. Les 14 lignes actuelles de `datas` et de `langchain_pg_embedding` sont déjà des morceaux de markdown qui se recouvrent (profil de juin, CV, addendum de septembre, Nova Games et BiblioNova dans le même espace). Un document de plus ajoute des voisins, il ne remplace pas les mauvais. Le classement par similarité mélange alors l’ancien et le nouveau.

Ordre :

1. Écrire les faits dans les tables canoniques (section 1). Insert ou update direct. C’est la correction.
2. Effacer le cache : toutes les lignes `datas`, puis les embeddings de la collection `cv_knowledge_base`.
3. Régénérer le cache depuis les tables, une entrée par fait, pas un chapitre entier.
   - Un projet actif = un chunk dont le texte est titre, slug, description, technologies.
   - Une expérience = un chunk.
   - La ligne d’identité, avec `cv_pdf`, = un chunk contact.
4. Métadonnées obligatoires sur chaque chunk : `source_table`, `source_id`, `category`, et `slug` pour un projet. `save_infos` sait déjà poser `category` dans les metadata pgvector.
5. Ré-ingérer avec le même `source_id` doit remplacer le chunk, pas en ajouter un second. Les doublons font chuter le ranking.

Retrieval, dans cet ordre :

- Liste, contact, PDF, « est-ce que tel projet existe » : SQL filtré (`est_actif`, `is_approved`). Pas de vecteur. Le rang est l’ordre métier (`ordre`), pas un score.
- Question qualitative : vecteur, filtré par `category` avant le tri par similarité. `top_k` dans cette catégorie seulement.
- Les deux seulement si la question mélange un fait et une explication. Les lignes SQL passent devant les chunks.

Le modèle interprète la question. S’il hésite entre deux cibles, il demande une reformulation et n’émet pas `[[guide]]`. S’il peut répondre sans page du site (détail déjà dans les lignes), il répond et n’émet pas `[[guide]]`. S’il redirige, le `slug` est celui de la ligne SQL, identique à la route du site.
