-- Vider la table des contacts clients (portet_clients)
-- À exécuter UNE SEULE FOIS dans Supabase → SQL Editor si vous voulez repartir de zéro.
-- Les messages outbound_messages gardent client_id = NULL (ON DELETE SET NULL).

-- Option 1 — recommandée : supprime les lignes, conserve l'historique des envois
UPDATE outbound_messages SET client_id = NULL WHERE client_id IS NOT NULL;

DELETE FROM portet_clients;

-- Vérification
-- SELECT COUNT(*) FROM portet_clients;

-- Option 2 — tout supprimer d'un coup (échoue si d'autres tables référencent portet_clients)
-- TRUNCATE TABLE portet_clients RESTART IDENTITY;
