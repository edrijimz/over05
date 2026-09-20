from __future__ import annotations
import requests

BASE = "https://www.thesportsdb.com/api/v1/json"

class TheSportsDB:
    def __init__(self, api_key: str = "123"):
        self.api_key = (api_key or "123").strip()
        self.session = requests.Session()

    def _get(self, endpoint: str, **params):
        url = f"{BASE}/{self.api_key}/{endpoint}"
        r = self.session.get(url, params=params, timeout=30)
        r.raise_for_status()
        return r.json()

    def events_day(self, day: str, sport: str = "Soccer"):
        return self._get("eventsday.php", d=day, s=sport).get("events") or []
