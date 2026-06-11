-- Boxeurs amateur et pro (table séparée des managers / promoteurs / coaches)
-- Apply via Supabase SQL Editor or: python scripts/apply_boxeurs_migration.py

DO $$ BEGIN
  CREATE TYPE boxeur_categorie_enum AS ENUM ('amateur', 'pro');
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS boxeurs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  nom TEXT NOT NULL,
  categorie boxeur_categorie_enum NOT NULL,
  email TEXT,
  telephone TEXT,
  adresse TEXT,
  localisation TEXT,
  url_profil TEXT,
  has_phone BOOLEAN NOT NULL DEFAULT FALSE,
  has_email BOOLEAN NOT NULL DEFAULT FALSE,
  contact_type contact_type_enum NOT NULL DEFAULT 'none',
  is_test BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS boxeurs_nom_categorie_normalized_idx
  ON boxeurs (lower(trim(nom)), categorie);

ALTER TABLE outbound_messages
  ADD COLUMN IF NOT EXISTS boxeur_id UUID REFERENCES boxeurs(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS outbound_messages_boxeur_id_idx
  ON outbound_messages (boxeur_id)
  WHERE boxeur_id IS NOT NULL;

ALTER TABLE boxeurs ENABLE ROW LEVEL SECURITY;
