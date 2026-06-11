# Boxing Center — Guide de déploiement complet

Deux dépôts GitHub :

| Repo | Rôle | URL |
|------|------|-----|
| [boxing-center-bot](https://github.com/angoularaphael/boxing-center-bot.git) | Bot WhatsApp + API + (optionnel) hébergement du site | Backend |
| [gestion-manager](https://github.com/angoularaphael/gestion-manager.git) | Console web (login, dashboard, envoi messages) | Frontend |

---

## Architecture

```
┌─────────────────────┐     ┌──────────────────┐     ┌─────────────┐
│  gestion-manager    │────▶│ boxing-center-bot│────▶│  Supabase   │
│  (Vercel ou VPS)    │ API │  (VPS 24/7)      │     │  managers   │
└─────────────────────┘     └────────┬─────────┘     └─────────────┘
                                     │
                            WhatsApp │ Email (Brevo)
                                     ▼
                              Managers boxe
```

**Recommandation début** : tout sur **un seul VPS** (le bot sert aussi le site) — plus simple pour WhatsApp + cookies.

**Séparé** : site sur Vercel + bot sur VPS → configurer `config.js` + `CORS_ORIGIN`.

---

## Étape 1 — Supabase (base de données)

1. Projet : https://ulxtbvxdueolvnjhpzvw.supabase.co  
2. Ouvrir **SQL Editor** : https://supabase.com/dashboard/project/ulxtbvxdueolvnjhpzvw/sql  
3. Coller et exécuter le fichier `supabase/migrations/001_boxing_center.sql`  
4. Récupérer dans **Settings → API** :
   - `Project URL`
   - `service_role` key (secret, jamais côté navigateur)
   - `anon` key (optionnel)

5. Importer les managers (depuis le dossier `infobox` parent si vous avez les CSV) :

```bash
pip install requests python-dotenv
python scripts/sync_managers_supabase.py
```

Sources : `managers_contacts_sans_doublons.csv` + `managers_enrichis.csv` (enrichi=oui) + test atangana.

---

## Étape 2 — Brevo (emails)

1. Créer un compte sur [Brevo](https://www.brevo.com/)  
2. **SMTP & API → Clés API** → créer une clé  
3. Vérifier l’expéditeur `boxingcenter31@gmail.com` (ou domaine)  
4. Noter la clé pour `BREVO_API_KEY`

---

## Étape 3 — Repo `boxing-center-bot`

### Fichiers à pousser sur GitHub

Contenu du dossier `boxing-center-bot/` :

```
boxing-center-bot/
├── index.js
├── users.js
├── supabase.js
├── email.js
├── package.json
├── assets/logo.png
├── .env.example
├── .gitignore
└── README.md
```

**Ne pas pousser** : `.env`, `auth_info_baileys/`, `node_modules/`, `users.json`, `bot_config.json`

### Commandes initiales

```bash
git clone https://github.com/angoularaphael/boxing-center-bot.git
cd boxing-center-bot
npm install
cp .env.example .env
```

### Fichier `.env` (à remplir)

```env
PORT=3002

# Supabase
SUPABASE_URL=https://ulxtbvxdueolvnjhpzvw.supabase.co
SUPABASE_SERVICE_ROLE_KEY=votre_service_role_jwt
SUPABASE_ANON_KEY=votre_cle_anon

# Sécurité API (scripts / intégrations)
SITE_API_SECRET=une_chaine_secrete_longue

# Super administrateur (créé au 1er démarrage)
SUPER_ADMIN_EMAIL=angoularaphael05@gmail.com
SUPER_ADMIN_PASSWORD=#Fareno12

# JWT (générer une chaîne aléatoire longue en production)
JWT_SECRET=changez_moi_en_production_32_caracteres_min

# WhatsApp admin obligatoire (indicatif sans +)
MANDATORY_ADMIN_PHONE=237693646080

# Site public Boxing Center
BOXING_CENTER_SITE_URL=https://boxingcenter.fr/

# Brevo
BREVO_API_KEY=votre_cle_brevo
BREVO_SENDER_EMAIL=boxingcenter31@gmail.com
BREVO_SENDER_NAME=Boxing Center

# Si le site gestion-manager est sur un autre domaine (Vercel)
# CORS_ORIGIN=https://votre-app.vercel.app
```

### Démarrer le bot (VPS)

```bash
npm start
# ou avec PM2 :
pm2 start index.js --name boxing-center-bot
pm2 save
```

Le bot expose l’API sur le port `3002`.

---

## Étape 4 — Repo `gestion-manager`

### Fichiers à pousser

Tout le contenu de `boxing-center-site/` :

```
gestion-manager/
├── index.html
├── config.js          # ou config.js.example + config en prod
├── css/app.css
├── js/
│   ├── app.js
│   ├── api.js
│   ├── router.js
│   └── pages/...
└── README.md
```

**Logo** : le site charge `/assets/logo.png` depuis le **bot**. En déploiement séparé, copier `assets/logo.png` dans `gestion-manager/public/assets/` ou pointer vers le bot.

### Option A — Même serveur que le bot (simple)

Modifier `boxing-center-bot/index.js` — le bot sert déjà `../boxing-center-site`.  
Clonez `gestion-manager` à côté ou intégrez les fichiers dans le bot.

Accès : `http://IP_DU_VPS:3002/login`

### Option B — Vercel (site séparé)

1. Importer [gestion-manager](https://github.com/angoularaphael/gestion-manager.git) sur Vercel  
2. Créer `config.js` à la racine :

```js
window.BC_CONFIG = {
  apiBase: 'https://VOTRE-BOT-VPS:3002',
};
```

3. Sur le bot, dans `.env` :

```env
CORS_ORIGIN=https://votre-gestion-manager.vercel.app
```

4. Ouvrir le port 3002 sur le VPS (pare-feu + reverse proxy HTTPS recommandé).

---

## Étape 5 — Connexion & super admin

1. Ouvrir `/login`  
2. Se connecter avec :
   - **Email** : `angoularaphael05@gmail.com`
   - **Mot de passe** : `#Fareno12`

Au **premier démarrage**, le bot crée automatiquement ce compte super admin (fichier `users.json` local).

### Créer des accès pour l’équipe

1. Aller dans **Paramètres** (`/dashboard/parametres`)  
2. Section **Gestion des accès** (visible uniquement pour `super_admin`)  
3. Renseigner email, mot de passe (min. 8 car.), rôle `admin` ou `super_admin`  
4. Les collaborateurs se connectent avec leur email + mot de passe

---

## Étape 6 — Lier WhatsApp

1. Dashboard → **WhatsApp** (`/dashboard/whatsapp`)  
2. Cliquer **Démarrer / QR**  
3. Scanner le QR avec le téléphone du compte WhatsApp Business  
4. La session est sauvegardée dans `auth_info_baileys/` (ne pas supprimer sur le VPS)

**Test** : envoyer un message test au manager **atangana** (+237693646080) depuis **Envoyer**.

---

## Étape 7 — Commandes WhatsApp du bot

Depuis un numéro **autorisé** (admin WhatsApp) :

| Commande | Action |
|----------|--------|
| `.menu` | Logo + lien [boxingcenter.fr](https://boxingcenter.fr/) + email support |
| `.guide` | Liste des commandes |
| `.numeros` | Managers avec téléphone |
| `.emails` | Managers avec email |
| `.stats` | Statistiques contacts |
| `.nonlus` | Messages WhatsApp non lus |
| `.authorise NUMERO` | Autoriser un admin WhatsApp |

---

## Étape 8 — Checklist finale

- [ ] Migration SQL Supabase exécutée  
- [ ] `python scripts/sync_managers_supabase.py` OK  
- [ ] `.env` du bot rempli (Supabase, Brevo, super admin)  
- [ ] Bot démarré sur VPS (`pm2`)  
- [ ] Login `angoularaphael05@gmail.com` fonctionne  
- [ ] WhatsApp connecté (QR)  
- [ ] Test email vers `linuxcam05@gmail.com` (atangana)  
- [ ] Test WhatsApp vers `+237693646080`  
- [ ] Site gestion-manager accessible (même VPS ou Vercel + CORS)

---

## Sécurité

- Ne jamais committer `.env`, `users.json`, clés Supabase/Brevo  
- Régénérer les clés si elles ont été exposées dans un chat  
- Utiliser **HTTPS** en production (Nginx + Let's Encrypt devant le bot)  
- Changer `JWT_SECRET` et mots de passe par défaut avant mise en prod

---

## Dépannage

| Problème | Solution |
|----------|----------|
| `Could not find table managers` | Exécuter la migration SQL Supabase |
| Login refusé | Vérifier `SUPER_ADMIN_EMAIL` / `SUPER_ADMIN_PASSWORD`, redémarrer le bot |
| CORS erreur depuis Vercel | `CORS_ORIGIN` + `config.js` apiBase |
| WhatsApp déconnecté | Rescanner QR, vérifier que `auth_info_baileys` persiste |
| Email non envoyé | Vérifier `BREVO_API_KEY` et expéditeur validé |
