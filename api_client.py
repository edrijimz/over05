from __future__ import annotations
import requests
from config import API_BASE, TIMEZONE

class ApiFootball:
    def __init__(self, api_key: str):
        self.api_key = api_key.strip()
        self.session = requests.Session()
        self.session.headers.update({"x-apisports-key": self.api_key})

    def _get(self, endpoint: str, **params):
        r = self.session.get(f"{API_BASE}/{endpoint}", params=params, timeout=25)
        r.raise_for_status()
        payload = r.json()
        if payload.get("errors"):
            raise RuntimeError(str(payload["errors"]))
        return payload.get("response", [])

    def fixtures_by_date(self, date: str):
        return self._get("fixtures", date=date, timezone=TIMEZONE)

    def team_last(self, team_id: int, last: int = 15):
        return self._get("fixtures", team=team_id, last=last, timezone=TIMEZONE)

    def h2h(self, home_id: int, away_id: int, last: int = 5):
        return self._get("fixtures/headtohead", h2h=f"{home_id}-{away_id}", last=last)
