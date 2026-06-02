# InfoBox — Collecte de contacts BoxRec

Application web pour extraire **nom**, **email** et **numéro de téléphone** des **managers**, **matchmakers** et **promoters** listés sur [BoxRec](https://boxrec.com), avec pagination automatique et exports CSV / PDF.

## Prérequis

- Python 3.10 ou plus récent
- Compte BoxRec (souvent **obligatoire** pour consulter les listes et profils)

## Installation

```bash
cd "d:\PROBOOK 445 G7\Desktop\Coach-brad\infobox"
python -m venv .venv

# Windows PowerShell
.\.venv\Scripts\Activate.ps1

pip install -r requirements.txt
copy .env.example .env
```

Éditez `.env` **ou** utilisez la page **Configuration** dans l’application (fichier `data/settings.json`) :

```env
BOXREC_USERNAME=votre_email
BOXREC_PASSWORD=votre_mot_de_passe
SCRAPE_DELAY_SECONDS=1.5
```

Les variables `.env` ont priorité sur le formulaire web.

## Lancement

```bash
python app.py
```

Ouvrez **http://127.0.0.1:5000/assistant** dans le navigateur.

## Pages (interface simplifiée)

| URL | Description |
|-----|-------------|
| `/` ou `/assistant` | **Assistant** : installer le favori + mode d’emploi |
| `/install-favori` | Page dédiée au glisser-déposer du favori |
| `/download/favori-infobox.html` | Fichier favori à importer dans Chrome |

Les anciennes pages (`/collecte`, `/configuration`, etc.) redirigent vers l’assistant.

## Utilisation

### Pour le client final (recommandé)

1. Ouvrez **http://127.0.0.1:5000/assistant** (une fois, pour installer le favori)
2. **Glissez** le bouton rouge **InfoBox v3.1** dans les favoris (ne mettez pas la page `/assistant` en favori avec l’étoile)
3. Connectez-vous sur boxrec.com, ouvrez une liste (managers, etc.)
4. Cliquez le favori → collecte automatique, puis **téléchargement CSV + PDF** (sans quitter BoxRec, sans `python app.py`)

### Pour les techniciens

1. **Configuration** — compte BoxRec (souvent bloqué en 403 par BoxRec)
2. **Collecte auto** ou **Mode manuel** (HTML collé)
3. **Résultats** — export CSV ou PDF

### Déploiement Vercel (recommandé pour le client)

Le site **Assistant + favori** est prêt pour Vercel. La collecte BoxRec reste dans le **navigateur du client** (favori), pas sur les serveurs Vercel — donc pas de 403 lié aux IP datacenter.

1. Poussez le dépôt sur GitHub et importez le projet dans [Vercel](https://vercel.com).
2. Variables d’environnement (Vercel → Settings → Environment Variables) :
   - `INFOBOX_PUBLIC_URL` = `https://votre-projet.vercel.app` (URL finale, **sans** slash final)
   - `FLASK_SECRET_KEY` = chaîne aléatoire longue
   - `INFOBOX_API_KEY` = (optionnel) clé pour bloquer l’abus des API serveur
3. Déployez. Ouvrez `https://votre-projet.vercel.app/assistant`.
4. **Réinstallez le favori** après déploiement (le lien doit pointer vers Vercel, plus `127.0.0.1`).

Fichiers ajoutés : `vercel.json`, `api/index.py`, `runtime.txt`.

**Sécurité** : en-têtes CSP, anti-bots, limite de débit, `robots.txt`, CORS limité à boxrec.com + votre domaine. Les routes `/api/scrape` etc. exigent `INFOBOX_API_KEY` si elle est définie.

**Local** : `python app.py` — pas besoin de `.env` pour le favori ; `INFOBOX_PUBLIC_URL` optionnel en local.

### Filtres géographiques par défaut

L’application reprend l’exemple UK fourni :

- Localisation : `United Kingdom` (`l[loc_txt]`, `l[location]=gb_15599`, `l[level_id]=gb`)
- Sexe : `m`

Modifiez les variables `BOXREC_*` dans `.env` pour d’autres pays.

Les exports CSV/PDF incluent **pays_recherche** (filtre BoxRec) et **adresse** (résidence + société sur la fiche). Le CSV est en **UTF-16** pour s’ouvrir correctement dans Excel (accents `Isère`, etc.).

BoxRec ne publie en général **pas d’adresse postale complète** — seulement résidence, société, e-mail et téléphone sur la fiche profil.

### Mode manuel (secours)

Si BoxRec renvoie une page de connexion ou bloque le serveur (403 / limite) :

1. Connectez-vous sur BoxRec dans **votre** navigateur.
2. Ouvrez la page liste (ex. managers UK).
3. Affichez le code source (`Ctrl+U`), copiez tout le HTML.
4. Collez-le dans la zone **Mode manuel** et cliquez **Parser le HTML collé**.

Les noms et liens profil sont extraits de la table `.dataTable`. Les emails / téléphones nécessitent en général le HTML des pages profil ou une collecte automatique avec identifiants valides.

## API (résumé)

| Méthode | Route | Description |
|---------|-------|-------------|
| `GET` | `/api/health` | État du serveur |
| `POST` | `/api/scrape` | Démarre une collecte (`role`, `max_pages`, `fetch_contacts`) |
| `GET` | `/api/scrape/<job_id>/stream` | Progression (SSE) |
| `POST` | `/api/parse/manual` | Parse HTML collé |
| `POST` | `/api/export/pdf` | PDF côté serveur |

## Tests locaux

```bash
python test_parser.py
```

## Limitations connues

- **Connexion BoxRec** : les listes et profils sont souvent réservés aux utilisateurs connectés ; sans `.env`, la collecte automatique échouera rapidement.
- **Anti-bot** : BoxRec peut renvoyer `403` ou rediriger vers `/login?error=limit`. Utilisez un délai suffisant (`SCRAPE_DELAY_SECONDS`), des identifiants valides, ou le mode manuel.
- **CORS** : le scraping passe par le backend Flask (pas d’appels directs depuis le navigateur vers BoxRec).
- **Données manquantes** : tous les profils n’affichent pas email ou téléphone ; les champs restent vides.
- **Usage responsable** : respectez les [conditions BoxRec](https://boxrec.com) ; usage personnel / informatif recommandé.

## Structure du projet

```
infobox/
├── app.py                 # Serveur Flask
├── scraper/
│   ├── boxrec_client.py   # HTTP, login, pagination
│   ├── parser.py          # Analyse HTML
│   └── export_utils.py    # CSV / PDF serveur
├── static/                # Interface web
├── fixtures/              # HTML d’exemple pour tests
├── requirements.txt
└── README.md
```

## Exemple d’URL BoxRec

```
https://boxrec.com/en/locations/people?l[role]=manager&l[loc_txt]=United%20Kingdom&l[location]=gb_15599&l[level_id]=gb&offset=40
```

Rôles valides testés : `manager`, `matchmaker`, `promoter`.
