APP_TITLE = "Over 0.5 Goal Analyzer"
OPENFOOT_API_BASE = "https://openfootapi.com/v1"
TIMEZONE = "America/Costa_Rica"
LOW_ODDS_THRESHOLD = 1.02

# Human-readable target list. Only these competitions belong to our analysis universe.
TARGET_LEAGUES = [
    ("Argentina", "Liga Profesional"), ("Argentina", "Primera Nacional"),
    ("Brazil", "Serie A"), ("Mexico", "Liga MX"), ("Colombia", "Primera A"),
    ("Costa Rica", "Primera Division"), ("USA", "MLS"), ("Peru", "Liga 1"),
    ("Uruguay", "Primera Division"), ("Spain", "La Liga"), ("Spain", "Segunda Division"),
    ("Italy", "Serie A"), ("Italy", "Serie B"), ("France", "Ligue 1"), ("France", "Ligue 2"),
    ("Germany", "Bundesliga"), ("Germany", "2. Bundesliga"), ("England", "Premier League"),
    ("England", "Championship"), ("Scotland", "Premiership"), ("Bulgaria", "First League"),
    ("Czech Republic", "First League"), ("Greece", "Super League"), ("Denmark", "Superliga"),
    ("Switzerland", "Super League"), ("Portugal", "Primeira Liga"), ("Norway", "Eliteserien"),
    ("Hungary", "NB I"), ("Netherlands", "Eredivisie"), ("Belgium", "Pro League"),
    ("Turkey", "Süper Lig"), ("Sweden", "Allsvenskan"),
]

# Known canonical IDs observed/confirmed from OpenFoot responses/docs.
# The remaining competitions are resolved from /competitions at runtime and displayed for review.
KNOWN_COMPETITION_IDS = {
    ("Colombia", "Primera A"): "comp_primera_a_col",
    ("Costa Rica", "Primera Division"): "comp_primera_division_crc",
    ("Peru", "Liga 1"): "comp_liga_1_per",
    ("Germany", "Bundesliga"): "comp_bundesliga_de",
    ("England", "Premier League"): "comp_premier_league_eng",
}

WEIGHTS = {
    "zero_zero": 35, "scoring": 25, "conceding": 20,
    "venue": 10, "h2h": 5, "coverage": 5,
}
