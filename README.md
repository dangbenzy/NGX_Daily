# NGX Telegram EOD Bot

A small scheduled bot that fetches Nigerian Exchange (NGX) end-of-day market movers and sends the top 5 gainers and top 5 losers to a private Telegram chat.

## What It Does

- Fetches NGX companies from NGN Market's free `/companies` endpoint.
- Formats the top 5 gainers and top 5 losers.
- Sends the message to Telegram.
- Runs every weekday after NGX market close through GitHub Actions.

The default schedule is **6:00 PM WAT, Monday-Friday**.

## Required Secrets

Create these GitHub Actions secrets in your repository:

| Secret | Description |
| --- | --- |
| `NGN_MARKET_API_KEY` | Your NGN Market API key |
| `TELEGRAM_BOT_TOKEN` | Token from Telegram BotFather |
| `TELEGRAM_CHAT_ID` | Your Telegram chat ID |

## Local Dry Run

PowerShell:

```powershell
$env:NGN_MARKET_API_KEY="ngm_live_your_key"
$env:TELEGRAM_BOT_TOKEN="123456:your_bot_token"
$env:TELEGRAM_CHAT_ID="123456789"
$env:DRY_RUN="true"
python main.py
```

`DRY_RUN=true` prints the message instead of sending it to Telegram.

## Send A Real Test Message

After confirming the dry run output:

```powershell
$env:DRY_RUN="false"
python main.py
```

## GitHub Actions Setup

1. Create a GitHub repository.
2. Push these files.
3. Go to `Settings -> Secrets and variables -> Actions`.
4. Add the three required secrets.
5. Go to `Actions -> NGX EOD Telegram Bot -> Run workflow` for a manual test.

The scheduled workflow uses UTC:

```yaml
cron: "0 17 * * 1-5"
```

That is **6:00 PM WAT**.

## Optional Environment Variables

| Variable | Default | Description |
| --- | --- | --- |
| `NGN_MARKET_BASE_URL` | `https://api.ngnmarket.com/v1` | API base URL |
| `NGN_MARKET_COMPANIES_PATH` | `/companies` | Free company list endpoint path |
| `BOT_LIMIT` | `5` | Number of gainers and losers |
| `DRY_RUN` | `false` | Print message instead of sending |
| `SKIP_STALE_DATA` | `true` | Skip sending if the API exposes an older data date |
| `HTTP_USER_AGENT` | `NGX-Daily-Bot/1.0...` | User agent sent to APIs |

## Troubleshooting

If `/market/movers` fails with:

```text
PLAN_REQUIRED
```

the NGN Market `/market/movers` endpoint is not available on the free plan. This bot uses the free `/companies` endpoint and computes the top gainers and losers locally.
