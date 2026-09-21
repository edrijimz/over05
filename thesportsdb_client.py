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

    def events_day(self, day: str, sport: str = "Soccer", league_id: str | None = None):
        params = {"d": day, "s": sport}
        if league_id:
            params["l"] = str(league_id)
        return self._get("eventsday.php", **params).get("events") or []

    def all_leagues(self):
        return self._get("all_leagues.php").get("leagues") or []

    def seasons(self, league_id: str):
        return self._get("search_all_seasons.php", id=str(league_id)).get("seasons") or []

    def season_events(self, league_id: str, season: str):
        return self._get("eventsseason.php", id=str(league_id), s=season).get("events") or []

    def next_league_events(self, league_id: str):
        return self._get("eventsnextleague.php", id=str(league_id)).get("events") or []

    def team_last_events(self, team_id: str):
        return self._get("eventslast.php", id=str(team_id)).get("results") or []

    def team_search(self, name: str):
        return self._get("searchteams.php", t=name).get("teams") or []

    def h2h(self, team1: str, team2: str):
        data = self._get("eventsh2h.php", h=team1, a=team2)
        return data.get("results") or data.get("events") or []
