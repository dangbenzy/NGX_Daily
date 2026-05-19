import json
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

from workers import Response, WorkerEntrypoint, fetch


LAGOS_TZ = timezone(timedelta(hours=1))
DEFAULT_USER_AGENT = "NGX-Daily-Bot/1.0 (+https://github.com/dangbenzy/NGX_Daily)"


class BotError(Exception):
    pass


def env_value(env, name, default=None):
    value = getattr(env, name, default)
    if value is None:
        return default
    return str(value).strip()


def require_env(env, name):
    value = env_value(env, name)
    if not value:
        raise BotError(f"Missing required environment variable: {name}")
    return value


def decimalish(value):
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return None


def first_present(item, keys):
    for key in keys:
        if key in item and item[key] not in (None, ""):
            return item[key]
    return None


def normalize_company(item):
    symbol = first_present(item, ("symbol", "ticker", "code", "security", "name"))
    price = first_present(
        item,
        (
            "close",
            "closing_price",
            "current_price",
            "last_price",
            "price",
            "today_close",
        ),
    )
    change_percent = first_present(
        item,
        (
            "change_percent",
            "percent_change",
            "percentage_change",
            "pct_change",
            "price_change_percent",
            "changePercentage",
        ),
    )
    return {
        "symbol": str(symbol or "UNKNOWN").upper(),
        "price": decimalish(price),
        "change_percent": decimalish(change_percent),
    }


def unwrap_data(payload):
    data = payload.get("data", payload)
    if isinstance(data, dict) and "data" in data and len(data) <= 3:
        nested = data.get("data")
        if isinstance(nested, list):
            return nested
    return data


async def fetch_json(url, headers=None):
    response = await fetch(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": DEFAULT_USER_AGENT,
            **(headers or {}),
        },
    )
    text = await response.text()
    if response.status < 200 or response.status >= 300:
        raise BotError(f"GET {url} failed with HTTP {response.status}: {text}")
    try:
        payload = json.loads(text)
    except ValueError as exc:
        raise BotError(f"GET {url} returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise BotError(f"GET {url} returned an unexpected JSON shape")
    return payload


async def post_json(url, payload):
    response = await fetch(
        url,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": DEFAULT_USER_AGENT,
        },
        body=json.dumps(payload),
    )
    text = await response.text()
    if response.status < 200 or response.status >= 300:
        raise BotError(f"POST {url} failed with HTTP {response.status}: {text}")
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise BotError(f"POST {url} returned invalid JSON") from exc
    if not isinstance(data, dict):
        raise BotError(f"POST {url} returned an unexpected JSON shape")
    return data


async def fetch_movers(env, limit):
    api_key = require_env(env, "NGN_MARKET_API_KEY")
    base_url = env_value(env, "NGN_MARKET_BASE_URL", "https://api.ngnmarket.com/v1").rstrip("/")
    path = "/" + env_value(env, "NGN_MARKET_COMPANIES_PATH", "/companies").strip("/")
    url = f"{base_url}{path}?limit=200&sort=price_change_percent&order=desc"
    payload = await fetch_json(url, headers={"Authorization": f"Bearer {api_key}"})

    if payload.get("success") is False:
        error = payload.get("error") or {}
        message = error.get("message") if isinstance(error, dict) else None
        raise BotError(f"NGN Market API returned an error: {message or payload}")

    data = unwrap_data(payload)
    if not isinstance(data, list):
        raise BotError("No companies list found in NGN Market response")

    movers = [normalize_company(item) for item in data if isinstance(item, dict)]
    movers = [item for item in movers if item["change_percent"] is not None]
    gainers = sorted(
        [item for item in movers if item["change_percent"] > 0],
        key=lambda item: item["change_percent"],
        reverse=True,
    )
    losers = sorted(
        [item for item in movers if item["change_percent"] < 0],
        key=lambda item: item["change_percent"],
    )
    if not gainers and not losers:
        raise BotError("No gainers or losers found in NGN Market response")
    return gainers[:limit], losers[:limit], payload


def money(value):
    if value is None:
        return "N/A"
    return f"N{value:,.2f}"


def percent(value):
    if value is None:
        return "N/A"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.2f}%"


def format_section(title, movers):
    if not movers:
        return f"{title}\nNo data available."

    lines = [title]
    for index, item in enumerate(movers, start=1):
        lines.append(f"{index}. {item['symbol']} {money(item['price'])} {percent(item['change_percent'])}")
    return "\n".join(lines)


def response_last_updated(payload):
    data = unwrap_data(payload)
    candidates = []
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                for key in ("last_updated", "lastUpdated", "updated_at", "updatedAt", "date"):
                    if item.get(key):
                        candidates.append(item[key])
    for key in ("last_updated", "lastUpdated", "updated_at", "updatedAt", "date"):
        if payload.get(key):
            candidates.append(payload[key])
    return str(candidates[0]) if candidates else None


def format_message(gainers, losers, payload):
    now = datetime.now(LAGOS_TZ)
    last_updated = response_last_updated(payload)
    data_line = f"Data: {last_updated}" if last_updated else "Data: End of day"
    return "\n\n".join(
        [
            f"NGX EOD Movers - {now:%d %b %Y}",
            format_section("Top 5 Gainers", gainers),
            format_section("Top 5 Losers", losers),
            f"{data_line}\nNot financial advice.\nEOD - {now:%d %b %Y}",
        ]
    )


async def send_telegram_message(env, text):
    bot_token = require_env(env, "TELEGRAM_BOT_TOKEN")
    chat_id = require_env(env, "TELEGRAM_CHAT_ID")
    response = await post_json(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True,
        },
    )
    if not response.get("ok"):
        raise BotError(f"Telegram API returned an error: {response}")


async def run_bot(env):
    limit = int(env_value(env, "BOT_LIMIT", "5"))
    if limit < 1:
        raise BotError("BOT_LIMIT must be a positive integer")
    gainers, losers, payload = await fetch_movers(env, limit)
    message = format_message(gainers, losers, payload)
    await send_telegram_message(env, message)
    return message


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        token = env_value(self.env, "MANUAL_TRIGGER_TOKEN")
        if not token:
            return Response(
                "NGX Daily bot is deployed. Scheduled runs do not need the public URL.",
                status=200,
            )

        request_url = urlparse(str(request.url))
        provided = parse_qs(request_url.query).get("token", [""])[0]
        if provided != token:
            return Response("Unauthorized", status=401)

        try:
            message = await run_bot(self.env)
            return Response(f"Telegram message sent.\n\n{message}", status=200)
        except Exception as exc:
            return Response(f"Error: {exc}", status=500)

    async def scheduled(self, controller, env, ctx):
        ctx.waitUntil(run_bot(env))
