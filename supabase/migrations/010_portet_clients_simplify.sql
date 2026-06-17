-- Simplifier portet_clients : nom, prenom, telephone, email, salle uniquement
-- Appliquer après 009_portet_clients.sql si déjà en place

ALTER TABLE portet_clients DROP COLUMN IF EXISTS adresse;
ALTER TABLE portet_clients DROP COLUMN IF EXISTS cours;
ALTER TABLE portet_clients DROP COLUMN IF EXISTS date_naissance;
ALTER TABLE portet_clients DROP COLUMN IF EXISTS pays;
ALTER TABLE portet_clients DROP COLUMN IF EXISTS region;
ALTER TABLE portet_clients DROP COLUMN IF EXISTS ville;
ALTER TABLE portet_clients DROP COLUMN IF EXISTS code_postal;
ALTER TABLE portet_clients DROP COLUMN IF EXISTS quartier;
ALTER TABLE portet_clients DROP COLUMN IF EXISTS numero_rue;
ALTER TABLE portet_clients DROP COLUMN IF EXISTS tag;
ALTER TABLE portet_clients DROP COLUMN IF EXISTS metier;
ALTER TABLE portet_clients DROP COLUMN IF EXISTS message;
ALTER TABLE portet_clients DROP COLUMN IF EXISTS recontact_requested;
ALTER TABLE portet_clients DROP COLUMN IF EXISTS chatbot_lead_id;
ALTER TABLE portet_clients DROP COLUMN IF EXISTS registered_at;

DROP INDEX IF EXISTS portet_clients_tag_idx;
DROP INDEX IF EXISTS portet_clients_registered_at_idx;

-- Autoriser source xls (export membres)
ALTER TABLE portet_clients DROP CONSTRAINT IF EXISTS portet_clients_source_check;
ALTER TABLE portet_clients ADD CONSTRAINT portet_clients_source_check
  CHECK (source IN ('chatbot', 'csv', 'xls', 'manual'));

-- Salle obligatoire pour nouveaux enregistrements chatbot (nullable pour imports historiques)
COMMENT ON TABLE portet_clients IS 'Clients Portet — champs contact : nom, prenom, telephone, email, salle';
