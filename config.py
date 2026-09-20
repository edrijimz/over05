APP_TITLE = "Over 0.5 Goal Analyzer"
OPENFOOT_API_BASE = "https://openfootapi.com/v1"
TIMEZONE = "America/Costa_Rica"
LOW_ODDS_THRESHOLD = 1.02

TARGET_LEAGUES = [
    ("Argentina", "Liga Profesional"), ("Argentina", "Primera Nacional"),
    ("Brazil", "Serie A"), ("Mexico", "Liga MX"), ("Colombia", "Primera A"),
    ("Costa Rica", "Primera Division"), ("USA", "MLS"), ("Peru", "Primera Division"),
    ("Uruguay", "Primera Division"), ("Spain", "LaLiga"), ("Spain", "Segunda Division"),
    ("Italy", "Serie A"), ("Italy", "Serie B"), ("France", "Ligue 1"), ("France", "Ligue 2"),
    ("Germany", "Bundesliga"), ("Germany", "2. Bundesliga"), ("England", "Premier League"),
    ("England", "Championship"), ("Scotland", "Premiership"), ("Bulgaria", "First League"),
    ("Czech Republic", "First League"), ("Greece", "Super League"), ("Denmark", "Superliga"),
    ("Switzerland", "Super League"), ("Portugal", "Primeira Liga"), ("Norway", "Eliteserien"),
    ("Hungary", "NB I"), ("Netherlands", "Eredivisie"), ("Belgium", "Pro League"),
    ("Turkey", "Süper Lig"), ("Sweden", "Allsvenskan"),
]

WEIGHTS = {
    "zero_zero": 35, "scoring": 25, "conceding": 20,
    "venue": 10, "h2h": 5, "coverage": 5,
}
