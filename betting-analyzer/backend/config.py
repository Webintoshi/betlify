from __future__ import annotations

import os

TRACKED_LEAGUES = {
    # Turkiye
    203: "Turkiye Super Lig",
    204: "Turkiye 1. Lig",
    # Avrupa Kulup Kupalari
    2: "UEFA Sampiyonlar Ligi",
    3: "UEFA Avrupa Ligi",
    848: "UEFA Konferans Ligi",
    # Buyuk 5 Lig
    39: "Premier League",
    40: "Championship",
    140: "La Liga",
    141: "La Liga 2",
    135: "Serie A",
    136: "Serie B",
    78: "Bundesliga",
    79: "2. Bundesliga",
    61: "Ligue 1",
    62: "Ligue 2",
    # Diger Onemli Ligler
    88: "Eredivisie",
    94: "Primeira Liga",
    144: "Jupiler Pro League",
    179: "Scottish Premiership",
    106: "Ekstraklasa",
    218: "Super Lig Avusturya",
    # Milli Takim
    4: "UEFA Uluslar Ligi",
    5: "UEFA Avrupa Sampiyonasi",
    6: "FIFA Dunya Kupasi",
    960: "UEFA Uluslar Ligi Play-off",
}

TRACKED_LEAGUE_IDS = list(TRACKED_LEAGUES.keys())

SOFASCORE_TOURNAMENT_IDS = {
    52: "Turkiye Super Lig",
    17: "UEFA Sampiyonlar Ligi",
    679: "UEFA Avrupa Ligi",
    1: "Premier League",
    8: "La Liga",
    23: "Serie A",
    35: "Bundesliga",
    34: "Ligue 1",
    37: "Eredivisie",
    238: "Primeira Liga",
}

SOFASCORE_TOURNAMENT_ID_SET = set(SOFASCORE_TOURNAMENT_IDS.keys())

DEFAULT_SEASON = int(os.getenv("DEFAULT_SEASON", "2024"))
