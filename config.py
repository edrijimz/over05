APP_TITLE = "Over 0.5 Goal Analyzer"
OPENFOOT_API_BASE = "https://openfootapi.com/v1"
TIMEZONE = "America/Costa_Rica"
LOW_ODDS_THRESHOLD = 1.02

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

# Competition names/aliases accepted from TheSportsDB.
# We intentionally filter by canonical league ID after resolving these names.
# Canonical TheSportsDB IDs verified for leagues where names have changed.
# IDs take precedence over alias matching.
TSDB_KNOWN_LEAGUE_IDS = {
    ("Mexico", "Liga MX"): "4350",
    ("Colombia", "Primera A"): "4497",
    ("Costa Rica", "Primera Division"): "4815",
    ("USA", "MLS"): "4346",
    ("Brazil", "Serie A"): "4351",
    ("Argentina", "Liga Profesional"): "4406",
    # National-team competitions
    ("International", "World Cup Qualifying CONMEBOL"): "5515",
    ("International", "World Cup Qualifying CONCACAF"): "5516",
    ("International", "World Cup Qualifying UEFA"): "5518",
}

TSDB_TARGET_ALIASES = {
    ("Argentina", "Liga Profesional"): ["Argentinian Primera Division", "Argentina Primera Division", "Liga Profesional Argentina"],
    ("Argentina", "Primera Nacional"): ["Argentinian Primera B Nacional", "Primera Nacional"],
    ("Brazil", "Serie A"): ["Brazilian Serie A", "Brazil Serie A"],
    ("Mexico", "Liga MX"): ["Mexican Primera League", "Liga MX"],
    ("Colombia", "Primera A"): ["Colombian Primera A", "Categoria Primera A"],
    ("Costa Rica", "Primera Division"): ["Costa Rica Liga FPD", "Costa Rican Primera Division"],
    ("USA", "MLS"): ["American Major League Soccer", "Major League Soccer", "MLS"],
    ("Peru", "Liga 1"): ["Peruvian Primera Division", "Peru Liga 1"],
    ("Uruguay", "Primera Division"): ["Uruguayan Primera Division"],
    ("Spain", "La Liga"): ["Spanish La Liga", "La Liga"],
    ("Spain", "Segunda Division"): ["Spanish La Liga 2", "Spanish Segunda Division"],
    ("Italy", "Serie A"): ["Italian Serie A"],
    ("Italy", "Serie B"): ["Italian Serie B"],
    ("France", "Ligue 1"): ["French Ligue 1"],
    ("France", "Ligue 2"): ["French Ligue 2"],
    ("Germany", "Bundesliga"): ["German Bundesliga"],
    ("Germany", "2. Bundesliga"): ["German 2. Bundesliga", "German Bundesliga 2"],
    ("England", "Premier League"): ["English Premier League"],
    ("England", "Championship"): ["English League Championship", "English Championship"],
    ("Scotland", "Premiership"): ["Scottish Premier League", "Scottish Premiership"],
    ("Bulgaria", "First League"): ["Bulgarian First League", "Bulgarian First Professional Football League"],
    ("Czech Republic", "First League"): ["Czech First League", "Czech Liga 1"],
    ("Greece", "Super League"): ["Greek Superleague", "Greek Super League"],
    ("Denmark", "Superliga"): ["Danish Superliga"],
    ("Switzerland", "Super League"): ["Swiss Super League"],
    ("Portugal", "Primeira Liga"): ["Portuguese Primeira Liga", "Portuguese Primera Liga"],
    ("Norway", "Eliteserien"): ["Norwegian Eliteserien"],
    ("Hungary", "NB I"): ["Hungarian NB I", "Hungarian Nemzeti Bajnoksag I"],
    ("Netherlands", "Eredivisie"): ["Dutch Eredivisie"],
    ("Belgium", "Pro League"): ["Belgian Pro League", "Belgian First Division A"],
    ("Turkey", "Süper Lig"): ["Turkish Super Lig", "Turkish Süper Lig"],
    ("Sweden", "Allsvenskan"): ["Swedish Allsvenskan"],
}

# International competitions approved for the radar. More national cups will be
# added by canonical ID as we validate them.
TSDB_EXTRA_COMPETITION_ALIASES = [
    "UEFA Champions League", "UEFA Europa League", "UEFA Europa Conference League",
    "Copa Libertadores", "Copa Sudamericana", "Recopa Sudamericana",
    "CONCACAF Champions Cup", "CONCACAF Central American Cup",
    "UEFA Nations League", "UEFA European Championship",
    "World Cup Qualifying UEFA", "World Cup Qualifying CONMEBOL",
    "World Cup Qualifying CONCACAF",
    "International Friendlies",
    "Copa America", "CONCACAF Gold Cup", "CONCACAF Nations League",
    "CONCACAF Gold Cup Qualifying",
]

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
