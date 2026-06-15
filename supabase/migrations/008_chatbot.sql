-- Chatbot Portet — leads et événements de suivi
-- Appliquer via Supabase SQL Editor

CREATE TABLE IF NOT EXISTS chatbot_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_type TEXT NOT NULL CHECK (
    event_type IN ('chat_started', 'lead_collected', 'faq_hit', 'faq_miss', 'escalation')
  ),
  session_id TEXT,
  faq_question TEXT,
  source TEXT DEFAULT 'portet',
  referrer TEXT,
  user_agent TEXT,
  ip_hash TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS chatbot_leads (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id TEXT,
  name TEXT,
  email TEXT,
  phone TEXT,
  metier TEXT,
  message TEXT,
  recontact_requested BOOLEAN NOT NULL DEFAULT false,
  source TEXT DEFAULT 'portet',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS chatbot_events_type_created_idx
  ON chatbot_events (event_type, created_at DESC);

CREATE INDEX IF NOT EXISTS chatbot_events_session_idx
  ON chatbot_events (session_id);

CREATE INDEX IF NOT EXISTS chatbot_leads_created_at_idx
  ON chatbot_leads (created_at DESC);

CREATE INDEX IF NOT EXISTS chatbot_leads_session_idx
  ON chatbot_leads (session_id);
