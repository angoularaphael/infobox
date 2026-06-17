-- Rétablit le 0 initial sur les numéros FR stockés à 9 chiffres (ex. 774865543 → 0774865543)
UPDATE portet_clients
SET telephone = '0' || telephone,
    updated_at = now()
WHERE telephone IS NOT NULL
  AND telephone ~ '^[1-9][0-9]{8}$';
