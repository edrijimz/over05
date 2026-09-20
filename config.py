APP_TITLE = "Over 0.5 Goal Analyzer"
API_BASE = "https://v3.football.api-sports.io"
TIMEZONE = "America/Costa_Rica"
LOW_ODDS_THRESHOLD = 1.02

# v1.0: intentionally conservative. Tune only after collecting out-of-sample results.
WEIGHTS = {
    "zero_zero": 35,
    "scoring": 25,
    "conceding": 20,
    "venue": 10,
    "h2h": 5,
    "coverage": 5,
}
