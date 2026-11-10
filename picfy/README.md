# Picfy

Picfy is the renamed Pixora social network. The Flask application in this folder uses the existing Supabase PostgreSQL database and Storage buckets; Messenger remains a separate app in the repository.

## Local run

1. Install Python 3.11+ and dependencies: `pip install -r requirements.txt`.
2. Copy `.env.example` to `.env` and fill in the values from the Supabase project settings.
3. Run `python app.py`.

## Vercel

Set the Vercel project's Root Directory to `picfy` and framework to Flask. Required environment variables:

- `SECRET_KEY`: long random session-signing secret.
- `DATABASE_URL`: Supabase PostgreSQL connection string (use the Session/Transaction Pooler and require SSL).
- `SUPABASE_URL`: `https://gamigpluabnzzynecbrl.supabase.co`.
- `SUPABASE_SERVICE_ROLE_KEY`: server-side Supabase secret. Never expose it in browser code, prefix it with `NEXT_PUBLIC_`, or commit it.

The app uses the existing `pixora-uploads`, `pixora-videos`, and `pixora-audio` buckets. Their names are kept to avoid breaking stored media references.

## Existing database

The app uses the existing `public.user`, `post`, `like`, `follow`, `story`, `comment`, `message`, `fons_transaction`, `fons_like_reward`, and `gift_sent` tables. It currently uses Flask-Login with password hashes in `public.user`; Supabase Auth has no users in this project yet.

## Security gate before public launch

The current Supabase security scan found RLS disabled on `public.user`, `story`, `comment`, `message`, `fons_transaction`, `fons_like_reward`, and `gift_sent`. It also found RLS enabled without policies on `post`, `like`, and `follow`. The disabled tables are exposed to the Supabase Data API; do not connect a browser client directly to these tables or launch the app publicly until access policies are reviewed and configured.

No database rows or buckets are changed by this repository setup.
