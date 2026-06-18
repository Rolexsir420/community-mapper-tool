# Deploying Community Mapper to Railway

## 0. Files in this project
```
community_mapper.py     - the bot itself (your code, unchanged)
generate_session.py     - run LOCALLY ONLY, generates SESSION_STRING
requirements.txt         - pinned deps (Pyrogram 2.0.106 + tgcrypto)
Procfile                 - tells Railway how to start the worker
railway.json              - builder/restart config
runtime.txt               - pins Python 3.11
.env.example              - template for required env vars
.gitignore                 - keeps .env and session files out of git
```

## 1. Generate your SESSION_STRING (on your own machine, not Railway)

```bash
pip install pyrogram tgcrypto
python generate_session.py
```

It'll ask for:
- `API_ID` and `API_HASH` — get these once from https://my.telegram.org/apps
- Your phone number
- The OTP Telegram sends you
- Your 2FA password, if you have one set

It prints a long string. **Copy it somewhere safe temporarily** (a password manager, not a chat). You'll paste it into Railway in step 3 and can then delete your local copy.

This string = full account access. If it ever leaks: Telegram Settings → Devices → end the unfamiliar session immediately, then generate a fresh one.

## 2. Push this folder to a GitHub repo

```bash
cd community_mapper
git init
git add .
git commit -m "Community mapper - initial deploy"
git remote add origin <your-repo-url>
git push -u origin main
```

`.gitignore` already excludes `.env` and `*.session` files, so nothing sensitive goes to GitHub as long as you don't manually `git add` a filled `.env`.

## 3. Create the Railway project

1. https://railway.app → **New Project** → **Deploy from GitHub repo** → pick this repo
2. Railway will detect `Procfile` / `railway.json` and use Nixpacks to build automatically
3. Go to the service's **Variables** tab and add each of these (values only, no quotes):

| Variable | Value |
|---|---|
| `API_ID` | from my.telegram.org |
| `API_HASH` | from my.telegram.org |
| `SESSION_STRING` | from step 1 |
| `LOG_CHANNEL` | numeric ID of your log channel, e.g. `-1001234567890` |
| `PRIMARY_GROUP` | numeric ID of your primary group |
| `SCAN_LIMIT` | `3000` (or whatever you want) |

4. Deploy. Check the **Deployments → Logs** tab — you should see Pyrogram connect, and within a few seconds the "✅ Community Mapper Online" message should land in your log channel.

## 4. Keep it running as a background worker, not a web service

This bot doesn't serve HTTP — it's a long-running Telegram client (`asyncio.Event().wait()` at the bottom keeps it alive). Railway will try to assign a public URL/health check by default for some service types, which this doesn't need.

In the service settings, under **Settings → Networking**, you can leave "Generate Domain" off — there's nothing to expose. As long as the process stays running (the Procfile's `worker:` line signals this isn't a web process), Railway just keeps it alive and restarts on crash per `railway.json`'s `restartPolicyType: ON_FAILURE`.

## 5. Common failure modes to know about

- **`AUTH_KEY_UNREGISTERED` / session invalid** → SESSION_STRING was generated with a different API_ID/API_HASH pair than what's in Railway's env vars, or the session was revoked from Telegram's Devices list. Regenerate.
- **Bot goes silent on big scans** → Pyrogram's `FloodWait` handling in your script retries the *whole group* from scratch on a flood wait. On a 3000-message scan this can repeat-loop if Telegram keeps flood-waiting you. Worth keeping an eye on Railway logs the first few runs.
- **Crash loop** → check logs for a missing/malformed env var first (e.g. `LOG_CHANNEL` not parseable as `int` because you pasted a `@username` instead of the numeric ID — it must be numeric, like `-100xxxxxxxxxx`).
- **Railway free tier sleep/usage limits** → confirm your plan supports always-on workers; some trial tiers limit monthly execution hours.

## 6. Updating the bot later

```bash
git add .
git commit -m "update"
git push
```
Railway auto-redeploys on push if you connected it via GitHub integration (default).
