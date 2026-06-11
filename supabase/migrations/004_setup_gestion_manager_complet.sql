-- =============================================================================
-- Boxing Center — gestion-manager : setup complet app_users
-- À exécuter dans Supabase → SQL Editor (une seule fois)
--
-- Super administrateur (angoularaphael05@gmail.com) :
--   configuré dans Vercel / .env.local — PAS dans cette table.
--   Seuls les administrateurs équipe sont stockés ici (rôle admin).
-- =============================================================================

-- 1. Table des administrateurs équipe
CREATE TABLE IF NOT EXISTS app_users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'admin',
  name TEXT,
  phone TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. Colonne téléphone (si table créée avant la migration 003)
ALTER TABLE app_users ADD COLUMN IF NOT EXISTS phone TEXT;

-- 3. Un seul type de rôle en base : admin
UPDATE app_users SET role = 'admin' WHERE role IS DISTINCT FROM 'admin';

ALTER TABLE app_users DROP CONSTRAINT IF EXISTS app_users_role_check;
ALTER TABLE app_users
  ADD CONSTRAINT app_users_role_check CHECK (role = 'admin');

-- 4. Index recherche par email
CREATE INDEX IF NOT EXISTS app_users_email_idx ON app_users (lower(email));

-- 5. Sécurité : accès via service role Next.js uniquement
ALTER TABLE app_users ENABLE ROW LEVEL SECURITY;

-- 6. Vérification
SELECT
  id,
  email,
  role,
  name,
  phone,
  created_at
FROM app_users
ORDER BY created_at;
