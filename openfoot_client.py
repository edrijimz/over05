from __future__ import annotations
import requests

OPENFOOT_BASE = "https://openfootapi.com/v1"

class OpenFoot:
    def __init__(self, api_key: str):
        self.api_key = api_key.strip()
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        })

    def _get(self, endpoint: str, **params):
        r = self.session.get(f"{OPENFOOT_BASE}/{endpoint}", params=params, timeout=30)
        try:
            payload = r.json()
        except ValueError:
            r.raise_for_status()
            raise RuntimeError("OpenFoot devolvió una respuesta no válida.")
        if not r.ok:
            err = payload.get("error", {}) if isinstance(payload, dict) else {}
            raise RuntimeError(err.get("message") or f"HTTP {r.status_code}")
        return payload.get("data", [])

    def health(self):
        return self._get("health")

    def competitions(self):
        return self._get("competitions")

    def matches_by_date(self, date_str: str):
        return self._get("matches", date=date_str)

    def search(self, query: str):
        return self._get("search", q=query)
