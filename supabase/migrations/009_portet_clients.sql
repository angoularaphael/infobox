-- Clients site Portet — champs contact uniquement
-- Appliquer via Supabase SQL Editor

CREATE TABLE IF NOT EXISTS portet_clients (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  nom TEXT,
  prenom TEXT,
  telephone TEXT,
  email TEXT,
  salle TEXT,
  source TEXT NOT NULL DEFAULT 'chatbot' CHECK (source IN ('chatbot', 'csv', 'xls', 'manual')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS portet_clients_email_unique_idx
  ON portet_clients (lower(trim(email)))
  WHERE email IS NOT NULL AND trim(email) <> '';

CREATE INDEX IF NOT EXISTS portet_clients_created_at_idx
  ON portet_clients (created_at DESC);

CREATE INDEX IF NOT EXISTS portet_clients_source_idx
  ON portet_clients (source);

CREATE INDEX IF NOT EXISTS portet_clients_salle_idx
  ON portet_clients (salle);

ALTER TABLE outbound_messages
  ADD COLUMN IF NOT EXISTS client_id UUID REFERENCES portet_clients(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS outbound_messages_client_id_idx
  ON outbound_messages (client_id);

ALTER TABLE portet_clients ENABLE ROW LEVEL SECURITY;
