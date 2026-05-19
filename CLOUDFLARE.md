# Cloudflare Worker Deployment

This deploys the NGX Telegram bot as a Cloudflare Python Worker with a Cron Trigger.

The current cron is:

```toml
crons = [ "0 16 * * MON-FRI" ]
```

Cloudflare cron uses UTC, so this runs at **5:00 PM WAT, Monday-Friday**.

## 1. Install Requirements

Install:

- Node.js
- `uv`

Cloudflare's Python Workers docs use `pywrangler`, which runs through `uv`.

## 2. Login To Cloudflare

```powershell
npx wrangler login
```

## 3. Install Python Worker Tooling

```powershell
uv sync
uv run pywrangler --help
```

## 4. Add Secrets

Run these one by one:

```powershell
npx wrangler secret put NGN_MARKET_API_KEY
npx wrangler secret put TELEGRAM_BOT_TOKEN
npx wrangler secret put TELEGRAM_CHAT_ID
npx wrangler secret put MANUAL_TRIGGER_TOKEN
```

Paste each value when prompted.

`MANUAL_TRIGGER_TOKEN` can be any long random string. It protects the public Worker URL from triggering Telegram messages.

## 5. Deploy

```powershell
uv run pywrangler deploy
```

## 6. Test Manually

After deployment, open the Worker URL with your manual trigger token:

```text
https://YOUR_WORKER.YOUR_SUBDOMAIN.workers.dev/?token=YOUR_MANUAL_TRIGGER_TOKEN
```

The `fetch` handler sends a Telegram message immediately and returns the message body.

You can also test the scheduled handler locally with:

```powershell
uv run pywrangler dev --test-scheduled
```

Then call:

```powershell
curl "http://localhost:8787/cdn-cgi/handler/scheduled"
```

## 7. Disable GitHub Schedule

After Cloudflare is confirmed working, remove or comment out the `schedule` block in `.github/workflows/daily.yml` so you do not receive duplicate messages.
