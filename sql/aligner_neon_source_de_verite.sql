-- =============================================================================
-- Alignement de Neon (neondb) sur le site — BACKEND_NEON_SOURCE_DE_VERITE.md §1
-- À relire puis exécuter à la main (console Neon ou psql). NON exécuté par le code.
--
-- Écrit d'après le schéma réel lu le 2026-09-25 :
--   - toutes les colonnes listées sont NOT NULL (sauf mention) et SANS valeur
--     par défaut en base (les défauts Django sont côté Python) → tout fournir ;
--   - id est une colonne IDENTITY : ne pas le fournir ;
--   - portfolio_app_projet.technologies / fonctionnalites / resultats sont du
--     TEXT contenant du JSON (pas de ::jsonb) ;
--     portfolio_app_experience.technologies / realisations sont du JSONB.
--
-- Partie A : prête à exécuter (aucune donnée inventée).
-- Partie B : modèles à compléter — les <…> sont à remplacer par tes vraies infos.
--
-- Ensuite :
--   python -m app.rebuild_knowledge_cache           (aperçu des faits)
--   python -m app.rebuild_knowledge_cache --apply   (régénère datas + embeddings)
--   python -m app.rebuild_knowledge_cache --check   (contrôles §6)
-- =============================================================================


-- =============================================================================
-- PARTIE A — prête
-- =============================================================================
BEGIN;

-- Slug = segment /projects/:slug du site
UPDATE portfolio_app_projet SET slug = 'super-cchic'    WHERE slug = 'super-cchic-pos-system';
UPDATE portfolio_app_projet SET slug = 'cv-chatbot-rag' WHERE slug = 'cv-chatbot-rag-system';
UPDATE portfolio_app_projet
   SET slug = 'wpf-manager', titre = 'Gestionnaire de projets', updated_at = NOW()
 WHERE slug = 'gestionnaire-projet-webnet';

-- Projet absent du site public → inactif (pas effacé)
UPDATE portfolio_app_projet SET est_actif = FALSE, updated_at = NOW() WHERE slug = 'nova-games-ecommerce';

-- Ordre d'affichage aligné sur le site (Nova passe en fin de liste)
UPDATE portfolio_app_projet SET ordre = 1 WHERE slug = 'super-cchic';
UPDATE portfolio_app_projet SET ordre = 2 WHERE slug = 'cv-chatbot-rag';
UPDATE portfolio_app_projet SET ordre = 4 WHERE slug = 'wpf-manager';
UPDATE portfolio_app_projet SET ordre = 99 WHERE slug = 'nova-games-ecommerce';

COMMIT;


-- =============================================================================
-- PARTIE B — à compléter puis exécuter
-- =============================================================================

-- B1. Profil (UNE seule ligne). photo et cv_pdf peuvent être NULL ; tout le
--     reste est obligatoire. telephone : obligatoire en base mais jamais exposé
--     par l'API ni le chat — '' est accepté. Max : cv_pdf 100 car.
-- INSERT INTO portfolio_app_infopersonnelle
--   (nom_complet, surnom, titre_professionnel, email, telephone, localisation,
--    bio_courte, bio_complete, photo, cv_pdf, linkedin, github, portfolio,
--    disponible, recherche_type)
-- VALUES
--   ('Yann Willy Jordan Pokam Teguia', 'Jordan', '<titre pro, 200 car.>',
--    '<email public>', '', '<ville, province>',
--    '<bio courte, 500 car.>', '<bio complète>',
--    NULL, '/CV_Jordan_Pokam_Teguia.pdf',
--    '<url linkedin>', '<url github>', '<url du site>',
--    TRUE, '<type de poste recherché>');

-- B2. Projets du site absents de la base (ordre 3 et 5)
-- INSERT INTO portfolio_app_projet
--   (titre, slug, description_courte, description, contexte, technologies,
--    fonctionnalites, resultats, url_github, url_demo, date_realisation,
--    est_mis_en_avant, est_actif, ordre, image, created_at, updated_at)
-- VALUES
--   ('SafetyHub', 'safety-hub', '<résumé, 300 car.>', '<description>', '<contexte>',
--    '["<techno 1>", "<techno 2>"]', '["<fonctionnalité>"]', '["<résultat>"]',
--    '', '', '<AAAA-MM-JJ>', FALSE, TRUE, 3, NULL, NOW(), NOW()),
--   ('L''Écrin de Julia''s', 'ecrin-de-julias', '<résumé, 300 car.>', '<description>', '<contexte>',
--    '["<techno 1>"]', '["<fonctionnalité>"]', '["<résultat>"]',
--    '', '', '<AAAA-MM-JJ>', FALSE, TRUE, 5, NULL, NOW(), NOW());

-- B3. Expériences (une ligne par poste). type_experience : 50 car. max
--     (ex. 'emploi', 'stage', 'entreprise'). date_fin NULL si en_cours.
-- INSERT INTO portfolio_app_experience
--   (titre, entreprise, type_experience, lieu, date_debut, date_fin, en_cours,
--    description, technologies, realisations, ordre_affichage, est_actif)
-- VALUES
--   ('<poste>', '<entreprise>', '<type>', '<lieu>', '<AAAA-MM-JJ>', NULL, TRUE,
--    '<description>', '["<techno>"]'::jsonb, '["<réalisation>"]'::jsonb, 1, TRUE);

-- B4. Formations. mention : obligatoire, '' si aucune.
-- INSERT INTO portfolio_app_formation
--   (titre, etablissement, lieu, date_debut, date_fin, en_cours, description,
--    diplome_obtenu, mention, ordre_affichage, est_actif)
-- VALUES
--   ('<diplôme>', '<établissement>', '<lieu>', '<AAAA-MM-JJ>', '<AAAA-MM-JJ>', FALSE,
--    '<description>', TRUE, '', 1, TRUE);

-- B5. Compétences (une ligne par techno). niveau : entier (ton échelle, ex. 1-5).
--     icone : obligatoire, '' accepté. categorie : 50 car. max.
-- INSERT INTO portfolio_app_competence
--   (nom, categorie, niveau, icone, description, ordre_affichage, est_actif)
-- VALUES
--   ('<techno>', '<backend|frontend|ia|devops|…>', <niveau>, '', '<description>', 1, TRUE);


-- =============================================================================
-- Contrôles (§6) — attendus : 5 slugs du site, cv_pdf renseigné
-- =============================================================================
-- SELECT slug, titre FROM portfolio_app_projet WHERE est_actif ORDER BY ordre;
-- SELECT cv_pdf IS NOT NULL AND cv_pdf <> '' FROM portfolio_app_infopersonnelle;
-- SELECT category, COUNT(*) FROM datas GROUP BY category;   -- après --apply
