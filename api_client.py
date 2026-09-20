from __future__ import annotations
from datetime import date, timedelta
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

    def fixtures_by_date(self, date_str: str):
        return self._get("fixtures", date=date_str, timezone=TIMEZONE)

    def team_recent(self, team_id: int, before_date: str, days: int = 240, limit: int = 15):
        """Free-plan compatible replacement for the restricted ?last= parameter."""
        end = date.fromisoformat(before_date) - timedelta(days=1)
        start = end - timedelta(days=days)
        rows = self._get(
            "fixtures", team=team_id, from_=start.isoformat(), to=end.isoformat(),
            timezone=TIMEZONE
        )
        # requests needs the literal API parameter 'from', not Python's reserved keyword.
        if not rows:
            rows = self._get("fixtures", team=team_id, **{
                "from": start.isoformat(), "to": end.isoformat(), "timezone": TIMEZONE
            })
        finished = [
            x for x in rows
            if x.get("goals", {}).get("home") is not None
            and x.get("goals", {}).get("away") is not None
        ]
        finished.sort(key=lambda x: x["fixture"]["date"], reverse=True)
        return finished[:limit]

    def team_recent_free(self, team_id: int, before_date: str, days: int = 240, limit: int = 15):
        end = date.fromisoformat(before_date) - timedelta(days=1)
        start = end - timedelta(days=days)
        rows = self._get("fixtures", team=team_id, **{
            "from": start.isoformat(), "to": end.isoformat(), "timezone": TIMEZONE
        })
        finished = [x for x in rows if x.get("goals",{}).get("home") is not None and x.get("goals",{}).get("away") is not None]
        finished.sort(key=lambda x: x["fixture"]["date"], reverse=True)
        return finished[:limit]

    def h2h_free(self, home_id: int, away_id: int, before_date: str, days: int = 2200, limit: int = 5):
        end = date.fromisoformat(before_date) - timedelta(days=1)
        start = end - timedelta(days=days)
        rows = self._get("fixtures/headtohead", h2h=f"{home_id}-{away_id}", **{
            "from": start.isoformat(), "to": end.isoformat()
        })
        rows.sort(key=lambda x: x["fixture"]["date"], reverse=True)
        return rows[:limit]
