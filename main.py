import json
import os
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


NGN_MARKET_BASE_URL = os.getenv("NGN_MARKET_BASE_URL", "https://api.ngnmarket.com/v1")
NGN_MARKET_COMPANIES_PATH = os.getenv("NGN_MARKET_COMPANIES_PATH", "/companies")
LAGOS_TZ = ZoneInfo("Africa/Lagos")
DEFAULT_USER_AGENT = os.getenv(
    "HTTP_USER_AGENT",
    "NGX-Daily-Bot/1.0 (+https://github.com/dangbenzy/NGX_Daily)",
)


class BotError(Exception):
    pass


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise BotError(f"Missing required environment variable: {name}")
    return value


def get_json(url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
    request_headers = {
        "Accept": "application/json",
        "User-Agent": DEFAULT_USER_AGENT,
    }
    request_headers.update(headers or {})
    request = Request(url, headers=request_headers, method="GET")
    try:
        with urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
    except HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise BotError(f"GET {url} failed with HTTP {exc.code}: {details}") from exc
    except URLError as exc:
        raise BotError(f"GET {url} failed: {exc.reason}") from exc

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise BotError(f"GET {url} returned invalid JSON") from exc

    if not isinstance(payload, dict):
        raise BotError(f"GET {url} returned an unexpected JSON shape")
    return payload


def post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=data,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": DEFAULT_USER_AGENT,
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
    except HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise BotError(f"POST {url} failed with HTTP {exc.code}: {details}") from exc
    except URLError as exc:
        raise BotError(f"POST {url} failed: {exc.reason}") from exc

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise BotError(f"POST {url} returned invalid JSON") from exc

    if not isinstance(payload, dict):
        raise BotError(f"POST {url} returned an unexpected JSON shape")
    return payload


def decimal_from(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value).replace(",", ""))
    except (InvalidOperation, ValueError):
        return None


def first_present(item: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in item and item[key] not in (None, ""):
            return item[key]
    return None


def normalize_mover(item: dict[str, Any]) -> dict[str, Any]:
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
    change = first_present(item, ("change", "price_change", "gain", "loss"))
    volume = first_present(item, ("volume", "shares_traded", "trade_volume"))

    return {
        "symbol": str(symbol or "UNKNOWN").upper(),
        "price": decimal_from(price),
        "change_percent": decimal_from(change_percent),
        "change": decimal_from(change),
        "volume": decimal_from(volume),
    }


def unwrap_data(payload: dict[str, Any]) -> Any:
    data = payload.get("data", payload)
    if isinstance(data, dict) and "data" in data and len(data) <= 3:
        nested = data.get("data")
        if isinstance(nested, (dict, list)):
            return nested
    return data


def get_list_by_keys(data: Any, keys: tuple[str, ...]) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    for key in keys:
        value = data.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def extract_movers(payload: dict[str, Any], limit: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    data = unwrap_data(payload)
    gainers = get_list_by_keys(data, ("gainers", "top_gainers", "topGainers", "advancers"))
    losers = get_list_by_keys(data, ("losers", "top_losers", "topLosers", "decliners"))

    if not gainers and not losers and isinstance(data, list):
        movers = [normalize_mover(item) for item in data if isinstance(item, dict)]
        movers = [item for item in movers if item["change_percent"] is not None]
        gainers = [item for item in movers if item["change_percent"] > 0]
        losers = [item for item in movers if item["change_percent"] < 0]
    else:
        gainers = [normalize_mover(item) for item in gainers]
        losers = [normalize_mover(item) for item in losers]

    gainers = sorted(
        [item for item in gainers if item["change_percent"] is not None],
        key=lambda item: item["change_percent"],
        reverse=True,
    )
    losers = sorted(
        [item for item in losers if item["change_percent"] is not None],
        key=lambda item: item["change_percent"],
    )
    return gainers[:limit], losers[:limit]


def fetch_ngn_market_movers(api_key: str, limit: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    base_url = NGN_MARKET_BASE_URL.rstrip("/")
    path = "/" + NGN_MARKET_COMPANIES_PATH.strip("/")
    query = urlencode({"limit": 200, "sort": "price_change_percent", "order": "desc"})
    url = f"{base_url}{path}?{query}"
    payload = get_json(url, headers={"Authorization": f"Bearer {api_key}"})

    if payload.get("success") is False:
        error = payload.get("error") or {}
        message = error.get("message") if isinstance(error, dict) else None
        raise BotError(f"NGN Market API returned an error: {message or payload}")

    data = unwrap_data(payload)
    if not isinstance(data, list):
        raise BotError("No companies list found in NGN Market response")

    movers = [normalize_mover(item) for item in data if isinstance(item, dict)]
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


def fetch_movers(limit: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    return fetch_ngn_market_movers(require_env("NGN_MARKET_API_KEY"), limit)


def money(value: Decimal | None) -> str:
    if value is None:
        return "N/A"
    return f"N{value:,.2f}"


def percent(value: Decimal | None, force_sign: bool = True) -> str:
    if value is None:
        return "N/A"
    sign = "+" if force_sign and value > 0 else ""
    return f"{sign}{value:.2f}%"


def format_section(title: str, movers: list[dict[str, Any]]) -> str:
    if not movers:
        return f"{title}\nNo data available."

    lines = [title]
    for index, item in enumerate(movers, start=1):
        lines.append(
            f"{index}. {item['symbol']} {money(item['price'])} {percent(item['change_percent'])}"
        )
    return "\n".join(lines)


def response_last_updated(payload: dict[str, Any]) -> str | None:
    data = unwrap_data(payload)
    candidates: list[Any] = []
    if isinstance(data, dict):
        candidates.extend(
            data.get(key)
            for key in (
                "last_updated",
                "lastUpdated",
                "updated_at",
                "updatedAt",
                "date",
                "trade_date",
                "tradeDate",
            )
        )
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                candidates.extend(
                    item.get(key)
                    for key in ("trade_date", "tradeDate", "updated_at", "updatedAt")
                )
    candidates.extend(
        payload.get(key)
        for key in ("last_updated", "lastUpdated", "updated_at", "updatedAt", "date")
    )
    stocks = payload.get("stocks")
    if isinstance(stocks, list):
        for item in stocks:
            if isinstance(item, dict):
                candidates.extend(
                    item.get(key)
                    for key in ("trade_date", "tradeDate", "updated_at", "updatedAt")
                )
    for value in candidates:
        if value:
            return str(value)
    return None


def parse_lagos_date(value: str | None) -> date | None:
    if not value:
        return None

    text = value.strip()
    if not text:
        return None

    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=LAGOS_TZ)
        return parsed.astimezone(LAGOS_TZ).date()
    except ValueError:
        pass

    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def has_stale_data(payload: dict[str, Any]) -> bool:
    last_updated = response_last_updated(payload)
    data_date = parse_lagos_date(last_updated)
    if data_date is None:
        return False
    return data_date != datetime.now(LAGOS_TZ).date()


def format_message(
    gainers: list[dict[str, Any]],
    losers: list[dict[str, Any]],
    payload: dict[str, Any],
) -> str:
    now = datetime.now(LAGOS_TZ)
    title = f"NGX EOD Movers - {now:%d %b %Y}"
    last_updated = response_last_updated(payload)
    data_line = f"Data: {last_updated}" if last_updated else "Data: End of day"
    return "\n\n".join(
        [
            title,
            format_section("Top 5 Gainers", gainers),
            format_section("Top 5 Losers", losers),
            f"{data_line}\nNot financial advice.",
        ]
    )


def send_telegram_message(bot_token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    response = post_json(url, payload)
    if not response.get("ok"):
        raise BotError(f"Telegram API returned an error: {response}")


def is_true(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def main() -> int:
    try:
        limit = int(os.getenv("BOT_LIMIT", "5"))
        if limit < 1:
            raise ValueError
    except ValueError:
        raise BotError("BOT_LIMIT must be a positive integer")

    bot_token = require_env("TELEGRAM_BOT_TOKEN")
    chat_id = require_env("TELEGRAM_CHAT_ID")

    gainers, losers, payload = fetch_movers(limit)

    if is_true(os.getenv("SKIP_STALE_DATA", "true")) and has_stale_data(payload):
        print(f"Skipping send because market data is stale: {response_last_updated(payload)}")
        return 0

    message = format_message(gainers, losers, payload)

    if is_true(os.getenv("DRY_RUN")):
        print(message)
        return 0

    send_telegram_message(bot_token, chat_id, message)
    print("Telegram message sent.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BotError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
