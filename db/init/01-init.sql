-- ========================================================================
-- 1. Charger l'extension pgvector dans la BD 'postgres'
-- ========================================================================
CREATE EXTENSION IF NOT EXISTS vector;

-- ========================================================================
-- 2. CRÉATION DES UTILISATEURS (DOUBLE SÉCURITÉ)
-- ========================================================================

-- A. Créer l'utilisateur 'admin' (minuscule - le standard)
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'admin') THEN
    CREATE ROLE admin WITH LOGIN PASSWORD 'Admin123' SUPERUSER CREATEDB;
  END IF;
END
$$;

-- B. Créer l'utilisateur "Admin" (Majuscule - pour satisfaire le dump capricieux)
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'Admin') THEN
    CREATE ROLE "Admin" WITH LOGIN PASSWORD 'Admin123' SUPERUSER CREATEDB;
  END IF;
END
$$;

-- ========================================================================
-- 3. Créer la base 'QuizDb' (On la donne à admin minuscule par défaut)
-- ========================================================================
SELECT 'CREATE DATABASE "QuizDb" OWNER admin ENCODING ''UTF8'''
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'QuizDb')
\gexec

-- ========================================================================
-- 4. Se connecter à QuizDb
-- ========================================================================
\c QuizDb postgres

-- Charger l'extension
CREATE EXTENSION IF NOT EXISTS vector;

-- ========================================================================
-- 5. Accorder les permissions AUX DEUX COMPTES
-- ========================================================================

-- Permissions pour 'admin' (minuscule)
GRANT ALL PRIVILEGES ON DATABASE "QuizDb" TO admin;
GRANT ALL PRIVILEGES ON SCHEMA public TO admin;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO admin;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO admin;

-- Permissions pour "Admin" (Majuscule)
GRANT ALL PRIVILEGES ON DATABASE "QuizDb" TO "Admin";
GRANT ALL PRIVILEGES ON SCHEMA public TO "Admin";
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO "Admin";
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO "Admin";