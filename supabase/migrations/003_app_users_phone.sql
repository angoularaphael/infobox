-- Téléphone + rôle admin uniquement en base (super admin = variables d'environnement)

ALTER TABLE app_users ADD COLUMN IF NOT EXISTS phone TEXT;

UPDATE app_users SET role = 'admin' WHERE role = 'super_admin';

ALTER TABLE app_users DROP CONSTRAINT IF EXISTS app_users_role_check;
ALTER TABLE app_users ADD CONSTRAINT app_users_role_check CHECK (role = 'admin');
