-- Offre Été 2026 — tracking des clics (WordPress) et vues (landing page)
-- Appliquer via Supabase SQL Editor

CREATE TABLE IF NOT EXISTS offre_ete_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_type TEXT NOT NULL CHECK (event_type IN ('click', 'view')),
  source TEXT,
  referrer TEXT,
  user_agent TEXT,
  ip_hash TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS offre_ete_events_type_created_idx
  ON offre_ete_events (event_type, created_at DESC);

CREATE INDEX IF NOT EXISTS offre_ete_events_created_at_idx
  ON offre_ete_events (created_at DESC);
