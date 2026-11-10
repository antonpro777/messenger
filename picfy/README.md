# Picfy

Picfy is the renamed Pixora social network. The Flask application in this folder uses Supabase PostgreSQL and the existing Storage buckets; Messenger remains a separate app in the repository.

## Local run

1. Install Python 3.11+ and dependencies: `pip install -r requirements.txt`.
2. Copy `.env.example` to `.env` and configure the database, SMTP sender, and Supabase Storage credentials.
3. Run `python app.py`.

## Authentication

Picfy now uses email one-time codes for registration and login. Codes are six digits, expire after 10 minutes, and allow up to five verification attempts. Email sending is configured with `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, and `MAIL_FROM`. Use an app password or SMTP credential from the mail provider; never commit it to GitHub or send it in chat.

Usernames must be 3–30 characters and contain only English letters, digits, or underscores. Common profanity and insulting terms are blocked. The filter is a basic moderation layer, not a guarantee that every abusive variation will be detected.

## Vercel

Set the Vercel project's Root Directory to `picfy` and framework to Flask. Required environment variables:

- `SECRET_KEY`: long random session-signing secret.
- `DATABASE_URL`: Supabase PostgreSQL connection string with SSL. The Flask backend must connect using the server-side database owner role that can operate with RLS enabled.
- `SUPABASE_URL`: `https://gamigpluabnzzynecbrl.supabase.co`.
- `SUPABASE_SERVICE_ROLE_KEY`: server-side Supabase secret for Storage operations only. Never expose it in browser code, prefix it with `NEXT_PUBLIC_`, or commit it.
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `MAIL_FROM`: credentials and sender address for the mailbox that sends verification codes.

The app uses the existing `pixora-uploads`, `pixora-videos`, and `pixora-audio` buckets. Their names remain unchanged.

## Database reset and RLS

The old Picfy account and social-content records were cleared from the ten existing application tables. Their table structures were retained so the app's social features can continue to use them. A new `public.email_code` table stores hashed, expiring verification codes.

RLS is enabled on all eleven application tables. No client-facing policies are created: the app is designed to access PostgreSQL from its server-side Flask backend, not directly from an anonymous browser client. Do not expose the database owner credentials or the Supabase service-role key to the browser. Confirm that the Vercel `DATABASE_URL` uses the server-side owner connection before deployment.

The database reset removed relational records. Existing objects in Supabase Storage buckets were not deleted by the database reset and may need a separate cleanup if you want all old uploaded media removed.
