import unittest
from decimal import Decimal

from main import extract_movers, format_message, parse_lagos_date


class MoversParsingTest(unittest.TestCase):
    def test_extracts_named_gainers_and_losers(self):
        payload = {
            "success": True,
            "data": {
                "gainers": [
                    {"symbol": "AAA", "close": "10.5", "change_percent": "5.25"},
                    {"symbol": "BBB", "close": "8", "change_percent": "3.1"},
                ],
                "losers": [
                    {"symbol": "CCC", "close": "2", "change_percent": "-4.2"},
                    {"symbol": "DDD", "close": "7", "change_percent": "-1.4"},
                ],
            },
        }

        gainers, losers = extract_movers(payload, 1)

        self.assertEqual(gainers[0]["symbol"], "AAA")
        self.assertEqual(gainers[0]["price"], Decimal("10.5"))
        self.assertEqual(losers[0]["symbol"], "CCC")

    def test_splits_flat_mover_list(self):
        payload = {
            "success": True,
            "data": [
                {"symbol": "AAA", "price": "10", "percent_change": "1"},
                {"symbol": "BBB", "price": "11", "percent_change": "-5"},
                {"symbol": "CCC", "price": "12", "percent_change": "3"},
            ],
        }

        gainers, losers = extract_movers(payload, 5)

        self.assertEqual([item["symbol"] for item in gainers], ["CCC", "AAA"])
        self.assertEqual([item["symbol"] for item in losers], ["BBB"])

    def test_supports_ngn_market_company_change_field(self):
        payload = {
            "success": True,
            "data": {
                "data": [
                    {"symbol": "AAA", "price": "10", "price_change_percent": "7.5"},
                    {"symbol": "BBB", "price": "11", "price_change_percent": "-2.25"},
                ]
            },
        }

        gainers, losers = extract_movers(payload, 5)

        self.assertEqual(gainers[0]["symbol"], "AAA")
        self.assertEqual(losers[0]["symbol"], "BBB")


class MessageFormattingTest(unittest.TestCase):
    def test_formats_message_with_sections(self):
        message = format_message(
            [{"symbol": "AAA", "price": Decimal("10"), "change_percent": Decimal("2.5")}],
            [{"symbol": "BBB", "price": Decimal("5"), "change_percent": Decimal("-1.25")}],
            {"data": {"last_updated": "2026-05-18T16:20:00+01:00"}},
        )

        self.assertIn("NGX EOD Movers", message)
        self.assertIn("Top 5 Gainers", message)
        self.assertIn("1. AAA N10.00 +2.50%", message)
        self.assertIn("1. BBB N5.00 -1.25%", message)
        self.assertIn("Not financial advice.", message)


class DateParsingTest(unittest.TestCase):
    def test_parses_iso_timestamp(self):
        self.assertEqual(str(parse_lagos_date("2026-05-18T16:20:00+01:00")), "2026-05-18")

    def test_parses_date_only(self):
        self.assertEqual(str(parse_lagos_date("2026-05-18")), "2026-05-18")


if __name__ == "__main__":
    unittest.main()
