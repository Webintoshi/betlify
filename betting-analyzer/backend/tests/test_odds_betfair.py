from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.odds_api_io import OddsApiIo
from services.odds_scraper import OddsScraperService


class BetfairParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scraper = OddsScraperService(supabase_client=None, odds_api_client=OddsApiIo(api_key="dummy"))

    def test_market_mapping_success(self) -> None:
        payload = {
            "bookmakers": {
                "Betfair Exchange": [
                    {
                        "name": "ML",
                        "odds": [
                            {
                                "home": "2.10",
                                "draw": "3.30",
                                "away": "3.80",
                                "layHome": "2.14",
                                "layDraw": "3.38",
                                "layAway": "3.92",
                                "depthHome": "120",
                                "depthDraw": "95",
                                "depthAway": "108",
                            }
                        ],
                    },
                    {
                        "name": "ML HT",
                        "odds": [
                            {
                                "home": "2.80",
                                "draw": "2.20",
                                "away": "4.20",
                                "layHome": "2.86",
                                "layDraw": "2.24",
                                "layAway": "4.30",
                                "depthHome": "70",
                                "depthDraw": "77",
                                "depthAway": "65",
                            }
                        ],
                    },
                    {
                        "name": "Both Teams To Score",
                        "odds": [
                            {
                                "yes": "1.95",
                                "no": "1.85",
                                "layYes": "1.99",
                                "layNo": "1.89",
                                "depthOver": "88",
                                "depthUnder": "92",
                            }
                        ],
                    },
                    {
                        "name": "Totals",
                        "odds": [
                            {
                                "hdp": 2.5,
                                "over": "1.90",
                                "under": "1.95",
                                "layOver": "1.94",
                                "layUnder": "1.99",
                                "depthOver": "200",
                                "depthUnder": "215",
                            }
                        ],
                    },
                    {
                        "name": "Totals HT",
                        "odds": [
                            {
                                "hdp": 0.5,
                                "over": "1.45",
                                "under": "3.10",
                                "layOver": "1.48",
                                "layUnder": "3.20",
                                "depthOver": "150",
                                "depthUnder": "90",
                            }
                        ],
                    },
                    {
                        "name": "Spread",
                        "odds": [
                            {
                                "hdp": -1.0,
                                "home": "2.50",
                                "away": "1.60",
                                "layHome": "2.57",
                                "layAway": "1.64",
                                "depthHome": "180",
                                "depthAway": "175",
                            }
                        ],
                    },
                ]
            }
        }

        odds, rejects = self.scraper._parse_event_odds(payload)
        self.assertGreater(len(odds), 0)
        self.assertIn("MS1", odds)
        self.assertIn("MSX", odds)
        self.assertIn("MS2", odds)
        self.assertIn("IY1", odds)
        self.assertIn("IYX", odds)
        self.assertIn("IY2", odds)
        self.assertIn("MS_O2.5", odds)
        self.assertIn("MS_U2.5", odds)
        self.assertIn("IY_O0.5", odds)
        self.assertIn("IY_U0.5", odds)
        self.assertIn("KG_VAR", odds)
        self.assertIn("KG_YOK", odds)
        self.assertIn("HCP_-1", odds)
        self.assertIn("HCP_+1", odds)
        self.assertEqual(rejects, {})

    def test_low_liquidity_rejected(self) -> None:
        payload = {
            "bookmakers": {
                "Betfair Exchange": [
                    {
                        "name": "ML",
                        "odds": [
                            {
                                "home": "2.00",
                                "draw": "3.20",
                                "away": "4.00",
                                "layHome": "2.03",
                                "layDraw": "3.28",
                                "layAway": "4.12",
                                "depthHome": "10",
                                "depthDraw": "10",
                                "depthAway": "10",
                            }
                        ],
                    }
                ]
            }
        }
        odds, rejects = self.scraper._parse_event_odds(payload)
        self.assertNotIn("MS1", odds)
        self.assertNotIn("MSX", odds)
        self.assertNotIn("MS2", odds)
        self.assertGreaterEqual(rejects.get("low_liquidity", 0), 1)

    def test_wide_spread_rejected(self) -> None:
        payload = {
            "bookmakers": {
                "Betfair Exchange": [
                    {
                        "name": "ML",
                        "odds": [
                            {
                                "home": "2.00",
                                "draw": "3.20",
                                "away": "4.00",
                                "layHome": "2.30",
                                "layDraw": "3.25",
                                "layAway": "4.04",
                                "depthHome": "120",
                                "depthDraw": "120",
                                "depthAway": "120",
                            }
                        ],
                    }
                ]
            }
        }
        odds, rejects = self.scraper._parse_event_odds(payload)
        self.assertNotIn("MS1", odds)
        self.assertIn("MSX", odds)
        self.assertIn("MS2", odds)
        self.assertGreaterEqual(rejects.get("wide_spread", 0), 1)


class RateGuardTests(unittest.TestCase):
    def test_should_skip_non_critical(self) -> None:
        client = OddsApiIo(api_key="dummy", max_req_per_hour=100)
        client.requests_remaining = 10
        self.assertTrue(client.should_skip_non_critical())
        client.requests_remaining = 30
        self.assertFalse(client.should_skip_non_critical())


if __name__ == "__main__":
    unittest.main()
