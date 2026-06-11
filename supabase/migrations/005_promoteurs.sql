-- Promoteurs (table séparée des managers / coaches)
-- Apply via Supabase SQL Editor or: python scripts/apply_migration_supabase.py

CREATE TABLE IF NOT EXISTS promoteurs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  nom TEXT NOT NULL,
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

CREATE UNIQUE INDEX IF NOT EXISTS promoteurs_nom_normalized_idx
  ON promoteurs (lower(trim(nom)));

ALTER TABLE outbound_messages
  ADD COLUMN IF NOT EXISTS promoter_id UUID REFERENCES promoteurs(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS outbound_messages_promoter_id_idx
  ON outbound_messages (promoter_id)
  WHERE promoter_id IS NOT NULL;

ALTER TABLE promoteurs ENABLE ROW LEVEL SECURITY;
