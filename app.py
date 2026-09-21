from __future__ import annotations
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup

from openfoot_client import OpenFoot
from thesportsdb_client import TheSportsDB
from database import evaluations, save_experiment, update_result, ensure_experiment_schema
from analysis_engine import summarize_tsdb, rate, venue_split_tsdb, summarize_h2h_tsdb, poisson_over05, risk_level
from config import TIMEZONE, TARGET_LEAGUES, KNOWN_COMPETITION_IDS, TSDB_TARGET_ALIASES, TSDB_EXTRA_COMPETITION_ALIASES, TSDB_KNOWN_LEAGUE_IDS

st.set_page_config(page_title="Over 0.5 Analyzer", page_icon="⚽", layout="wide")
st.title("⚽ Over 0.5 Goal Analyzer")
st.caption("TheSportsDB Premium · horarios mostrados en hora de Costa Rica (UTC−6).")

with st.sidebar:
    st.header("Configuración")
    api_key = st.secrets.get("OPENFOOT_API_KEY", "") if hasattr(st, "secrets") else ""
    tsdb_key = st.secrets.get("THESPORTSDB_API_KEY", "123") if hasattr(st, "secrets") else "123"
    page = st.radio("Sección", ["Radar", "Experimento", "Cobertura", "Historial", "Metodología"])

@st.cache_data(ttl=3600, show_spinner=False)
def get_competitions(key):
    return OpenFoot(key).competitions()

@st.cache_data(ttl=300, show_spinner=False)
def get_match_meta(key, day):
    d = date.fromisoformat(day)
    api = OpenFoot(key)
    a = api.matches_envelope(date=d.isoformat())
    b = api.matches_envelope(date=(d + timedelta(days=1)).isoformat())
    return {
        d.isoformat(): a.get("meta", {}),
        (d + timedelta(days=1)).isoformat(): b.get("meta", {}),
    }

@st.cache_data(ttl=1800, show_spinner=False)
def get_matches_cr_day(key, day):
    # OpenFoot filters "date" in UTC. A Costa Rica calendar day spans two UTC dates.
    d = date.fromisoformat(day)
    api = OpenFoot(key)
    rows = api.matches_by_date(d.isoformat()) + api.matches_by_date((d + timedelta(days=1)).isoformat())
    seen = {}
    for m in rows:
        if m.get("id"):
            seen[m["id"]] = m
    target = d
    return [
        m for m in seen.values()
        if m.get("kickoffAt") and cr_time(m["kickoffAt"]).date() == target
    ]

def cr_time(iso):
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return dt.astimezone(ZoneInfo(TIMEZONE))

def competition_fields(c):
    name = c.get("name") or c.get("competitionName") or c.get("title") or ""
    country = c.get("country")
    if isinstance(country, dict):
        country = country.get("name") or country.get("code")
    country = country or c.get("area") or c.get("countryName") or ""
    if isinstance(country, dict):
        country = country.get("name") or country.get("code") or ""
    return str(country), str(name)

def norm(s):
    import unicodedata
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return "".join(ch if ch.isalnum() else " " for ch in s)

COUNTRY_ALIASES = {
    "USA": ["usa", "united states", "united states of america", "canada"],
    "Czech Republic": ["czech republic", "czechia"],
    "England": ["england"],
    "Scotland": ["scotland"],
}

LEAGUE_ALIASES = {
    "La Liga": ["la liga", "laliga", "primera division"],
    "Liga 1": ["liga 1", "primera division"],
    "MLS": ["mls", "major league soccer"],
    "NB I": ["nb i", "otp bank liga"],
    "Serie A": ["serie a"],
    "2. Bundesliga": ["2 bundesliga", "2. bundesliga", "zweite bundesliga"],
    "Pro League": ["pro league", "jupiler pro league"],
}

def resolve_competitions(comps):
    resolved = {}
    for target in TARGET_LEAGUES:
        if target in KNOWN_COMPETITION_IDS:
            resolved[target] = KNOWN_COMPETITION_IDS[target]
            continue
        country, league = target
        countries = COUNTRY_ALIASES.get(country, [country])
        leagues = LEAGUE_ALIASES.get(league, [league])
        candidates = []
        for c in comps:
            cc, cn = competition_fields(c)
            text_country, text_name = norm(cc), norm(cn)
            country_ok = any(norm(x) in text_country or norm(x) in norm(f"{cc} {cn}") for x in countries)
            league_ok = any(norm(x) in text_name for x in leagues)
            if country_ok and league_ok:
                cid = c.get("id") or c.get("competitionId")
                if cid:
                    candidates.append((cid, cn, cc))
        if len(candidates) == 1:
            resolved[target] = candidates[0][0]
    return resolved

@st.cache_data(ttl=3600, show_spinner=False)
def get_tsdb_whitelist(key):
    api = TheSportsDB(key)
    leagues = api.all_leagues()

    def clean(value):
        import unicodedata
        value = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().lower()
        return " ".join(value.replace("-", " ").replace("_", " ").split())

    wanted = list(TSDB_TARGET_ALIASES.items())
    wanted += [(("International", alias), [alias]) for alias in TSDB_EXTRA_COMPETITION_ALIASES]

    resolved = dict(TSDB_KNOWN_LEAGUE_IDS)
    for target, aliases in wanted:
        if target in resolved:
            continue
        alias_set = {clean(a) for a in aliases}
        for league in leagues:
            if clean(league.get("strSport")) != "soccer":
                continue
            if clean(league.get("strLeague")) in alias_set or clean(league.get("strLeagueAlternate")) in alias_set:
                if league.get("idLeague"):
                    resolved[target] = str(league["idLeague"])
                    break
    return resolved

@st.cache_data(ttl=3600, show_spinner=False)
def get_team_form_tsdb(key, team_id):
    return TheSportsDB(key).team_last_events(str(team_id))

@st.cache_data(ttl=3600, show_spinner=False)
def resolve_tsdb_team_id(key, team_id, team_name):
    """Use fixture team id first; recover by team name when TSDB returns a stale/missing id."""
    api = TheSportsDB(key)
    candidates = []
    if team_id:
        candidates.append(str(team_id))
    try:
        for t in api.team_search(team_name):
            tid = t.get("idTeam")
            if tid and str(tid) not in candidates:
                candidates.append(str(tid))
    except Exception:
        pass
    # Prefer a candidate whose returned events really belong to that team.
    # TSDB can return rows under a stale/duplicate team id; accepting merely
    # a non-empty response later produces 0 valid matches in summarize_tsdb.
    best_tid, best_events, best_valid = None, [], 0
    for tid in candidates:
        try:
            events = api.team_last_events(tid)
        except Exception:
            continue
        valid = [
            e for e in events
            if str(tid) in {
                str(e.get("idHomeTeam") or ""),
                str(e.get("idAwayTeam") or ""),
            }
            and e.get("intHomeScore") is not None
            and e.get("intAwayScore") is not None
        ]
        if len(valid) > best_valid:
            best_tid, best_events, best_valid = tid, events, len(valid)
        if best_valid >= 5:
            return best_tid, best_events
    return (best_tid or (candidates[0] if candidates else None)), best_events

@st.cache_data(ttl=3600, show_spinner=False)
def get_tsdb_season_events(key, league_id, season):
    if not league_id or not season:
        return []
    try:
        return TheSportsDB(key).season_events(str(league_id), str(season))
    except Exception:
        return []

def tsdb_team_history_from_season(events, team_id, before_date, limit=10):
    """Build recent team history from the league season when eventslast is incomplete."""
    if not team_id:
        return []
    rows = []
    for e in events or []:
        if str(team_id) not in {str(e.get("idHomeTeam") or ""), str(e.get("idAwayTeam") or "")}:
            continue
        if e.get("intHomeScore") is None or e.get("intAwayScore") is None:
            continue
        event_date = str(e.get("dateEvent") or "")[:10]
        if before_date and event_date and event_date >= before_date:
            continue
        rows.append(e)
    rows.sort(
        key=lambda e: (str(e.get("dateEvent") or ""), str(e.get("strTime") or "")),
        reverse=True,
    )
    return rows[:limit]

def merge_tsdb_history(primary, fallback, team_id, limit=10):
    """Merge team endpoint + season endpoint without duplicating events."""
    merged, seen = [], set()
    for e in list(primary or []) + list(fallback or []):
        if str(team_id) not in {str(e.get("idHomeTeam") or ""), str(e.get("idAwayTeam") or "")}:
            continue
        eid = str(e.get("idEvent") or "")
        key = eid or (
            str(e.get("dateEvent") or ""),
            str(e.get("idHomeTeam") or ""),
            str(e.get("idAwayTeam") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        merged.append(e)
    merged.sort(
        key=lambda e: (str(e.get("dateEvent") or ""), str(e.get("strTime") or "")),
        reverse=True,
    )
    return merged[:limit]

@st.cache_data(ttl=3600, show_spinner=False)
def get_h2h_tsdb(key, home_name, away_name):
    try:
        return TheSportsDB(key).h2h(home_name, away_name)
    except Exception:
        return []

@st.cache_data(ttl=300, show_spinner=False)
def get_oddschecker_over05(day, competition_names=()):
    """Obtiene O0.5 desde el JSON que usa Oddschecker Accumulator."""
    cards = "30175,9155204,9098782,9020854,7350881,75,19061,8706,8705,28780,79,19065,9123568,80,8631121,16658,19082,15845,17515,33566,9117862,9041024,9041023,9105385,9084556,31412,90,10706,10704,9156048,10869,10928,10867,10879,16586,10873,10926,9100891,10846,22521,9118464,20311,18334,16285,18629,11638,281,8707,24002,26227,9076483,9085251,24412,23954,9117395,18499,8079172,11641,24094,9112681,24439,11635,10095,11722,17225,8738,10890,24263,10903,422039,10894,11715,26102,13400,17495,24067,18347,23980,8677499,16839,26671,4958315,11782,17319,11780,10892,10900,13525,19031,11717,23852,10184,19073,9092469,11719,8197690,17683,421835,19039,18112,416270,27688,18348,26338,30199,18503,18289,422333,422723,9088192,20471,27769,24547"
    url = (
        "https://www.oddschecker.com/api/acca/v1/acca/coupon/cards/"
        f"{cards}/marketTemplate/9/loadDataFor/3/forDate/{day}/andDays/1"
    )
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/153 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.oddschecker.com/football/accumulator",
        "Accept-Language": "en-GB,en;q=0.9",
    }
    try:
        # Discover extra competition cards from Oddschecker's Leagues & Cups
        # directory. This avoids maintaining every league/card id manually.
        discovered_cards = set()
        discovery = {"league_links": 0, "league_pages_checked": 0, "extra_cards": []}
        try:
            directory_url = "https://www.oddschecker.com/football/leagues-cups"
            dr = requests.get(directory_url, headers=headers, timeout=8)
            dr.raise_for_status()
            dsoup = BeautifulSoup(dr.text, "html.parser")
            links = []
            for a in dsoup.find_all("a", href=True):
                href = a.get("href", "")
                label = " ".join(a.stripped_strings)
                if "/football/" in href and label:
                    links.append((label, href))

            discovery["league_links"] = len(links)

            def league_tokens(value):
                stop = {"league", "liga", "division", "primera", "serie", "the", "de", "football", "soccer"}
                return {x for x in norm(value).split() if len(x) >= 2 and x not in stop}

            chosen = []
            for comp in competition_names:
                ct = league_tokens(comp)
                best = None
                best_score = 0.0
                for label, href in links:
                    lt = league_tokens(label)
                    if not ct or not lt:
                        continue
                    score = len(ct & lt) / max(1, len(ct | lt))
                    # Strong exact/containment bonus for names such as MLS.
                    if norm(label).strip() == norm(comp).strip():
                        score = 1.0
                    elif norm(label).strip() in norm(comp) or norm(comp).strip() in norm(label):
                        score = max(score, 0.75)
                    if score > best_score:
                        best, best_score = (label, href), score
                if best and best_score >= 0.45:
                    chosen.append((best_score, best[0], best[1]))

            # Fetch only leagues actually present in today's Radar.
            seen_urls = set()
            import re
            # Avoid one HTTP request per Radar competition. The Accumulator
            # already covers many leagues; cap discovery pages to keep reloads fast.
            chosen = sorted(chosen, reverse=True)[:8]
            for _score, label, href in chosen:
                full = href if href.startswith("http") else "https://www.oddschecker.com" + href
                if full in seen_urls:
                    continue
                seen_urls.add(full)
                lr = requests.get(full, headers=headers, timeout=6)
                if not lr.ok:
                    continue
                discovery["league_pages_checked"] += 1
                txt = lr.text

                # League pages expose cards in embedded config, e.g. cards:[{id:75}].
                for pat in (
                    r'"cards"\s*:\s*\[\s*\{\s*"id"\s*:\s*(\d+)',
                    r'cards\s*:\s*\[\s*\{\s*id\s*:\s*(\d+)',
                    r'"cardId"\s*:\s*(\d+)',
                ):
                    for cid in re.findall(pat, txt):
                        discovered_cards.add(cid)

            discovery["extra_cards"] = sorted(discovered_cards)
        except Exception as de:
            discovery["discovery_error"] = str(de)

        if discovered_cards:
            base_cards = set(cards.split(","))
            cards = ",".join(list(base_cards | discovered_cards))
            url = (
                "https://www.oddschecker.com/api/acca/v1/acca/coupon/cards/"
                f"{cards}/marketTemplate/9/loadDataFor/3/forDate/{day}/andDays/1"
            )

        r = requests.get(url, headers=headers, timeout=12)
        r.raise_for_status()
        data = r.json()

        # Index every subevent (fixture).
        subevents = {}
        for se in data.get("subevents", []):
            sid = se.get("id")
            if sid is not None:
                subevents[sid] = {
                    "home": se.get("homeTeamName", ""),
                    "away": se.get("awayTeamName", ""),
                }

        # Oddschecker keeps markets, bets and bookmaker prices in separate
        # collections in some responses. Walk the full JSON and build the
        # relationships instead of assuming one nesting shape.
        market_to_subevent = {}
        bet_to_subevent = {}
        over_bet_ids = set()
        price_objects = []

        def walk(obj, inherited_sid=None, inherited_market_id=None):
            if isinstance(obj, dict):
                sid = obj.get("subeventId", inherited_sid)
                market_id = obj.get("ocMarketId", obj.get("marketId", inherited_market_id))

                if sid is not None and market_id is not None:
                    market_to_subevent[market_id] = sid

                mtid = obj.get("marketTemplateId")
                generic = str(obj.get("genericName", obj.get("betName", ""))).upper()
                line = str(obj.get("line", ""))
                bid = obj.get("ocBetId", obj.get("betId"))

                if mtid == 9 and line == "0.5" and generic == "OVER" and bid is not None:
                    over_bet_ids.add(bid)
                    if sid is not None:
                        bet_to_subevent[bid] = sid
                    elif market_id in market_to_subevent:
                        bet_to_subevent[bid] = market_to_subevent[market_id]

                if bid is not None and "decimal" in obj:
                    price_objects.append(obj)

                for v in obj.values():
                    walk(v, sid, market_id)
            elif isinstance(obj, list):
                for v in obj:
                    walk(v, inherited_sid, inherited_market_id)

        walk(data)

        # Second pass: bets may only carry marketId while the market object
        # carrying subeventId appeared elsewhere.
        def link_bets(obj):
            if isinstance(obj, dict):
                bid = obj.get("ocBetId", obj.get("betId"))
                market_id = obj.get("marketId", obj.get("ocMarketId"))
                if bid in over_bet_ids and bid not in bet_to_subevent and market_id in market_to_subevent:
                    bet_to_subevent[bid] = market_to_subevent[market_id]
                for v in obj.values():
                    link_bets(v)
            elif isinstance(obj, list):
                for v in obj:
                    link_bets(v)
        link_bets(data)

        best = {}
        for p in price_objects:
            bid = p.get("betId", p.get("ocBetId"))
            if bid not in over_bet_ids:
                continue
            sid = bet_to_subevent.get(bid)
            if sid is None:
                continue
            try:
                dec = float(p.get("decimal"))
            except (TypeError, ValueError):
                continue
            if dec <= 1:
                continue
            # Use the best available O0.5 decimal quote across bookmakers.
            if sid not in best or dec > best[sid]:
                best[sid] = dec

        found = []
        seen = set()
        for sid, dec in best.items():
            teams = subevents.get(sid)
            if not teams or not teams["home"] or not teams["away"]:
                continue
            key = (norm(teams["home"]), norm(teams["away"]))
            if key in seen:
                continue
            seen.add(key)
            found.append({
                "home": teams["home"],
                "away": teams["away"],
                "odds": round(dec, 3),
                "source": "Oddschecker API",
            })

        diag = {
            "HTTP": r.status_code,
            "subevents": len(subevents),
            "markets_linked": len(market_to_subevent),
            "over_bet_ids": len(over_bet_ids),
            "over_bets_linked": len(bet_to_subevent),
            "prices_found": len(price_objects),
            "matched_prices": len(found),
            "league_links": discovery.get("league_links", 0),
            "league_pages_checked": discovery.get("league_pages_checked", 0),
            "extra_cards": discovery.get("extra_cards", []),
            "discovery_error": discovery.get("discovery_error"),
        }
        return found, None, diag
    except Exception as e:
        return [], str(e), {"url_date": day}

def match_reference_odd(home, away, odds_rows):
    def tokens(name):
        stop = {"fc","cf","afc","sc","club","de","the","united"}
        return {x for x in norm(name).split() if len(x) >= 3 and x not in stop}
    ht, at = tokens(home), tokens(away)
    best, best_score = None, 0.0
    for item in odds_rows:
        oh, oa = tokens(item["home"]), tokens(item["away"])
        hs = len(ht & oh) / max(1, len(ht | oh))
        aas = len(at & oa) / max(1, len(at | oa))
        score = (hs + aas) / 2
        if score > best_score:
            best, best_score = item, score
    return (best["odds"], best_score) if best and best_score >= 0.34 else (None, best_score)

@st.cache_data(ttl=1800, show_spinner=False)
def get_whitelist_matches(key, day):
    # One request per resolved competition. OpenFoot's default match window covers
    # today +/- 3 days, so we filter that response locally to the selected CR date.
    # This keeps a 32-league refresh below Starter's 60 req/min limit.
    d = date.fromisoformat(day)
    api = OpenFoot(key)
    comps = api.competitions()
    mapping = resolve_competitions(comps)
    rows, errors = [], []

    for target, cid in mapping.items():
        try:
            envelope = api.matches_envelope(competition=cid)
            unavailable = envelope.get("meta", {}).get("unavailable")
            if unavailable:
                errors.append((target, f"No disponible: {unavailable}"))
                continue
            for m in envelope.get("data", []):
                if m.get("kickoffAt") and cr_time(m["kickoffAt"]).date() == d:
                    m["_target"] = target
                    rows.append(m)
        except Exception as e:
            errors.append((target, str(e)))

    unique = {m.get("id", f"{m.get('competitionId')}-{m.get('kickoffAt')}"): m for m in rows}
    return list(unique.values()), mapping, errors

if page == "Cobertura" and not api_key:
    st.error("Falta OPENFOOT_API_KEY en Streamlit Secrets para consultar la cobertura de OpenFoot.")
    st.stop()

if page == "Cobertura":
    st.subheader("Prueba de cobertura de nuestras 32 ligas")
    st.caption("Esta pantalla no analiza partidos todavía. Comprueba qué competiciones reconoce OpenFoot para decidir el mapeo definitivo.")
    try:
        comps = get_competitions(api_key)
        rows = []
        for country, league in TARGET_LEAGUES:
            words = {w.lower() for w in league.replace(".", "").split() if len(w) > 2}
            candidates = []
            for c in comps:
                cc, cn = competition_fields(c)
                text = f"{cc} {cn}".lower()
                hits = sum(w in text for w in words)
                country_hit = country.lower() in text
                if hits and (country_hit or hits >= 2):
                    candidates.append((hits + int(country_hit), cn, cc, c.get("id") or c.get("competitionId")))
            candidates.sort(reverse=True)
            best = candidates[0] if candidates else None
            rows.append({
                "País objetivo": country,
                "Liga objetivo": league,
                "Estado": "✅ Encontrada" if best else "⚠️ Sin coincidencia",
                "OpenFoot": best[1] if best else "",
                "País API": best[2] if best else "",
                "ID": best[3] if best else "",
            })
        df = pd.DataFrame(rows)
        a, b, c = st.columns(3)
        a.metric("Configuradas", len(df))
        b.metric("Coincidencias", int((df["Estado"] == "✅ Encontrada").sum()))
        c.metric("Por revisar", int((df["Estado"] != "✅ Encontrada").sum()))
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.info("Una 'coincidencia' es provisional: después fijaremos manualmente los IDs correctos para evitar confundir ligas con nombres parecidos.")
    except Exception as e:
        st.error(f"No se pudo consultar OpenFoot: {e}")

elif page == "Radar":
    today_cr = datetime.now(ZoneInfo(TIMEZONE)).date()
    d = st.date_input("Fecha", today_cr)
    provider = st.selectbox("Proveedor de fixtures", ["TheSportsDB (prueba)", "OpenFoot"])
    status_filter = "Programados"
    morning_start, morning_end = time(3, 0), time(12, 0)
    afternoon_start, afternoon_end = time(12, 15), time(23, 30)
    league_mapping, league_errors = {}, []
    try:
        if provider.startswith("TheSportsDB"):
            # A Costa Rica calendar day overlaps two UTC calendar dates.
            # Fetch both so evening matches in CR (already next day in UTC)
            # stay under the correct local date.
            api_tsdb = TheSportsDB(tsdb_key)
            tsdb_mapping = get_tsdb_whitelist(tsdb_key)
            allowed_ids = set(tsdb_mapping.values())

            # Stable Radar: two bulk Schedule Day requests cover one full
            # Costa Rica calendar day across the UTC boundary. Keep the app
            # lightweight and avoid per-league calls/rate-limit problems.
            raw_all = (
                api_tsdb.events_day(d.isoformat(), "Soccer")
                + api_tsdb.events_day((d + timedelta(days=1)).isoformat(), "Soccer")
            )

            # eventsday.php does not always expose every fixture from some
            # competitions even when TSDB has those matches in the season
            # schedule. UWCL is one confirmed example. Merge its season
            # schedule before applying the whitelist/date filters.
            uwcl_id = tsdb_mapping.get(("International", "UEFA Womens Champions League"))
            if uwcl_id:
                try:
                    seasons = api_tsdb.seasons(str(uwcl_id))
                    season_names = [
                        str(s.get("strSeason") or s.get("season") or "")
                        for s in seasons
                        if (s.get("strSeason") or s.get("season"))
                    ]
                    # Prefer a season containing the selected year; the API
                    # normally returns the current/relevant season first.
                    selected_year = str(d.year)
                    season_name = next(
                        (s for s in season_names if selected_year in s),
                        season_names[0] if season_names else None,
                    )
                    if season_name:
                        raw_all += get_tsdb_season_events(
                            tsdb_key, str(uwcl_id), season_name
                        )
                except Exception:
                    pass

            raw_all = list({
                str(e.get("idEvent")): e
                for e in raw_all
                if e.get("idEvent")
            }.values())
            raw = [
                e for e in raw_all
                if str(e.get("idLeague") or "") in allowed_ids
            ]

            def tsdb_status(e):
                s = str(e.get("strStatus") or "").upper().strip()
                if s in {"NS", "TBD", "NOT STARTED", "SCHEDULED"} or not s:
                    return "scheduled"
                if s in {"1H", "HT", "2H", "ET", "BT", "P", "LIVE", "IN PLAY"}:
                    return "live"
                if s in {"FT", "AET", "PEN", "MATCH FINISHED"}:
                    return "finished"
                if s in {"PST", "CANC", "ABD", "SUSP", "AWD", "WO"}:
                    return "inactive"
                return "unknown"

            matches = []
            for e in raw:
                status = tsdb_status(e)
                # Radar = pre-match only. Finished, live, postponed and cancelled
                # events remain useful for history but never appear here.
                if status != "scheduled":
                    continue
                # Prefer TheSportsDB's full timestamp. It is the safest
                # source for timezone conversion. We already fetch two API dates,
                # so evening CR fixtures that cross the UTC date boundary are kept.
                stamp = e.get("strTimestamp")
                if stamp:
                    kickoff = stamp
                    if kickoff.endswith("Z"):
                        kickoff = kickoff[:-1] + "+00:00"
                    elif "+" not in kickoff[10:] and "-" not in kickoff[10:]:
                        kickoff = kickoff + "+00:00"
                else:
                    event_date = e.get("dateEvent") or d.isoformat()
                    event_time = e.get("strTime") or "00:00:00"
                    kickoff = f"{event_date}T{event_time}+00:00"
                # Keep only events whose converted kickoff belongs to the
                # selected Costa Rica calendar date.
                if cr_time(kickoff).date() != d:
                    continue
                matches.append({
                    "id": e.get("idEvent"),
                    "_raw": e,
                    "kickoffAt": kickoff,
                    "competitionName": e.get("strLeague") or "",
                    "competitionId": e.get("idLeague") or "",
                    "homeTeam": {"name": e.get("strHomeTeam") or "", "id": e.get("idHomeTeam")},
                    "awayTeam": {"name": e.get("strAwayTeam") or "", "id": e.get("idAwayTeam")},
                    "status": status,
                })
        else:
            matches, league_mapping, league_errors = get_whitelist_matches(api_key, d.isoformat())
    except Exception as e:
        st.error(f"No se pudieron cargar los partidos: {e}")
        st.stop()

    # El Radar solo muestra partidos que todavía no comenzaron.
    matches = [m for m in matches if m.get("status") == "scheduled"]

    radar_competitions = set()
    for _m in matches:
        _comp = _m.get("competition") or {}
        _name = _comp.get("name") if isinstance(_comp, dict) else ""
        _name = _name or _m.get("competitionName") or ""
        _target = _m.get("_target")
        if _target:
            _name = _target[1]
        if _name:
            radar_competitions.add(str(_name))

    odds_rows, odds_error, odds_diag = get_oddschecker_over05(
        d.isoformat(), tuple(sorted(radar_competitions))
    )

    rows = []
    for m in matches:
        comp = m.get("competition") or {}
        comp_name = comp.get("name") if isinstance(comp, dict) else ""
        comp_name = comp_name or m.get("competitionName") or m.get("competitionId") or ""
        target = m.get("_target")
        if target:
            comp_name = f"{target[0]} · {target[1]}"
        home = m.get("homeTeam") or {}
        away = m.get("awayTeam") or {}
        kickoff_raw = m.get("kickoffAt")
        kickoff = cr_time(kickoff_raw) if kickoff_raw else None
        analysis_score, analysis_label = None, "⚪ Pendiente"
        tsdb_note = ""
        home_form = away_form = home_venue = away_venue = None
        h2h_n = h2h_zz = 0
        model_p = None
        risk_label, risk_score, risk_reasons = "⚪ Sin evaluar", 0, []
        if provider.startswith("TheSportsDB") and m.get("_raw"):
            event = m["_raw"]
            home_id, away_id = event.get("idHomeTeam"), event.get("idAwayTeam")
            try:
                home_id, home_events = resolve_tsdb_team_id(
                    tsdb_key, home_id, event.get("strHomeTeam") or home.get("name", "")
                )
                away_id, away_events = resolve_tsdb_team_id(
                    tsdb_key, away_id, event.get("strAwayTeam") or away.get("name", "")
                )
                # eventslast.php can be incomplete for some TSDB competitions.
                # Premium also gives us the whole league season, so use it as a
                # fallback and build each team's previous matches from that data.
                league_id = event.get("idLeague")
                season = event.get("strSeason")
                fixture_date = str(event.get("dateEvent") or "")[:10]
                season_events = get_tsdb_season_events(tsdb_key, league_id, season)
                home_season = tsdb_team_history_from_season(
                    season_events, home_id, fixture_date, 10
                )
                away_season = tsdb_team_history_from_season(
                    season_events, away_id, fixture_date, 10
                )
                home_events = merge_tsdb_history(home_events, home_season, home_id, 10)
                away_events = merge_tsdb_history(away_events, away_season, away_id, 10)

                home_form = summarize_tsdb(home_events, str(home_id), 10) if home_id else None
                away_form = summarize_tsdb(away_events, str(away_id), 10) if away_id else None
                home_venue = venue_split_tsdb(home_events, str(home_id), "home", 10) if home_id else None
                away_venue = venue_split_tsdb(away_events, str(away_id), "away", 10) if away_id else None
                h2h_events = get_h2h_tsdb(
                    tsdb_key, event.get("strHomeTeam") or "", event.get("strAwayTeam") or ""
                )
                h2h_n, h2h_zz = summarize_h2h_tsdb(h2h_events, 5)
                if home_form and away_form:
                    model_p = poisson_over05(home_form, away_form)
                    risk_label, risk_score, risk_reasons = risk_level(
                        home_form, away_form, home_venue, away_venue, h2h_zz, h2h_n
                    )
                if home_form and away_form and home_form.matches >= 5 and away_form.matches >= 5:
                    analysis_score, analysis_label = rate(home_form, away_form, h2h_zz, h2h_n)
                else:
                    hn = home_form.matches if home_form else 0
                    an = away_form.matches if away_form else 0
                    analysis_label = "⚪ Datos insuficientes"
                    tsdb_note = f"TSDB válidos: local {hn}, visitante {an}"
            except Exception as e:
                analysis_label = "⚪ Datos insuficientes"
                tsdb_note = f"TSDB error: {type(e).__name__}"

        ref_odd, odds_match_score = match_reference_odd(home.get("name",""), away.get("name",""), odds_rows)
        odds_range = "✅ 1.02–1.08" if ref_odd is not None and 1.02 <= ref_odd <= 1.08 else ("⬜ Fuera de rango" if ref_odd is not None else "—")

        rows.append({
            "Hora CR": kickoff.strftime("%I:%M %p").lstrip("0") if kickoff else "",
            "_dt": kickoff,
            "Competición": comp_name,
            "Partido": f'{home.get("name","")} – {away.get("name","")}',
            "0-0 Local": f"{home_form.zero_zero}/{home_form.matches}" if home_form else "—",
            "0-0 Visit.": f"{away_form.zero_zero}/{away_form.matches}" if away_form else "—",
            "Marca ≥1": (f"{round(100*home_form.scored/home_form.matches)}% / {round(100*away_form.scored/away_form.matches)}%" if home_form and away_form and home_form.matches and away_form.matches else "—"),
            "Recibe ≥1": (f"{round(100*home_form.conceded/home_form.matches)}% / {round(100*away_form.conceded/away_form.matches)}%" if home_form and away_form and home_form.matches and away_form.matches else "—"),
            "Casa/Fuera 0-0": (f"{home_venue.zero_zero}/{home_venue.matches} · {away_venue.zero_zero}/{away_venue.matches}" if home_venue and away_venue else "—"),
            "H2H 0-0": f"{h2h_zz}/{h2h_n}" if h2h_n else "—",
            "P(+0.5) modelo": f"{model_p}%" if model_p is not None else "—",
            "Score +0.5": analysis_score if analysis_score is not None else "—",
            "Cuota O0.5 ref.": ref_odd if ref_odd is not None else "—",
            "Rango cuota": odds_range,
            "_odds_match_score": round(odds_match_score, 2),
            "Riesgo": risk_label,
            "_risk_score": risk_score,
            "_risk_reasons": tuple(risk_reasons),
            "_fixture_id": m.get("id"),
            "_kickoff_raw": kickoff_raw,
            "_home": home.get("name",""),
            "_away": away.get("name",""),
            "_home_zz": home_form.zero_zero if home_form else None,
            "_home_n": home_form.matches if home_form else None,
            "_away_zz": away_form.zero_zero if away_form else None,
            "_away_n": away_form.matches if away_form else None,
            "_model_p_num": model_p,
            "_tsdb_note": tsdb_note,
            "Estado": analysis_label,
            "_home_scores": home_form.scores if home_form else (),
            "_away_scores": away_form.scores if away_form else (),
        })

    if not rows:
        st.info(f"{provider} no devolvió partidos para esta fecha con los filtros actuales.")
        if provider.startswith("TheSportsDB"):
            st.caption("La prueba gratuita de TheSportsDB tiene datos/endpoints limitados. Esto no significa que Premium carezca de partidos; primero estamos validando la conexión y la respuesta del endpoint.")
            st.subheader("Diagnóstico · TheSportsDB")
            st.write(f"**Eventos recibidos antes del filtro de estado: {len(raw)}**")
            st.write(f"Fecha consultada: {d.isoformat()}")
            st.write(f"Estado seleccionado: {status_filter}")
            if raw:
                st.write("Muestra de la respuesta:")
                st.json(raw[:3])
            else:
                st.warning("La API devolvió 0 eventos antes de que nuestra aplicación aplicara cualquier filtro.")
        else:
            st.caption("Revisa el diagnóstico de OpenFoot o prueba otro estado/fecha.")
    else:
        df = pd.DataFrame(rows)
        df = df.sort_values("_dt", na_position="last")
        st.write(f"**{len(df)} partidos programados de la whitelist para {d.isoformat()} (hora Costa Rica)**")
        if provider == "OpenFoot":
            st.caption(f"Ligas resueltas: {len(league_mapping)}/{len(TARGET_LEAGUES)} · máximo una consulta por liga cada 30 min")
        else:
            st.caption(f"TheSportsDB Premium · whitelist activa · {len(tsdb_mapping)} competiciones resueltas")
        if league_errors:
            st.warning(f"{len(league_errors)} consultas de liga tuvieron error; revisa Diagnóstico OpenFoot.")
        morning = int(sum(morning_start <= x.time() <= morning_end for x in df["_dt"] if pd.notna(x)))
        afternoon = int(sum(afternoon_start <= x.time() <= afternoon_end for x in df["_dt"] if pd.notna(x)))
        outside = len(df) - morning - afternoon
        a, b, c, dcol = st.columns(4)
        a.metric("Mostrados", len(df))
        b.metric("Mañana · 3:00 AM–12:00 PM", morning)
        c.metric("Tarde · 12:15 PM–11:30 PM", afternoon)
        dcol.metric("Fuera de tandas", outside)
        st.info("Score +0.5 experimental basado en resultados recientes de TheSportsDB. Es un índice de perfil, no una probabilidad calibrada.")
        if odds_error:
            st.warning(f"Cuotas de referencia no disponibles temporalmente: {odds_error}")
        elif not odds_rows:
            st.caption("Oddschecker respondió, pero no se pudieron interpretar cuotas O0.5 en esta carga.")
        else:
            matched_odds = int((df["Cuota O0.5 ref."] != "—").sum())
            st.caption(f"Cuotas O0.5 de referencia: {len(odds_rows)} partidos leídos de Oddschecker · {matched_odds}/{len(df)} emparejados con el Radar · caché 5 min · confirmar precio final en bet365.")
            with st.expander("Diagnóstico · cuotas O0.5"):
                st.write(f"Partidos leídos de Oddschecker: {len(odds_rows)}")
                st.write(f"Partidos del Radar con coincidencia: {matched_odds}/{len(df)}")
                if odds_rows:
                    st.dataframe(pd.DataFrame(odds_rows[:30]), use_container_width=True, hide_index=True)
                st.write("**Diagnóstico API Oddschecker**")
                st.json(odds_diag)
        with st.expander(f"Diagnóstico · {provider}"):
            st.caption("Información técnica para validar qué proveedor está ejecutando el Radar.")
            if provider.startswith("TheSportsDB"):
                st.write("**Competiciones TheSportsDB resueltas por la whitelist**")
                st.dataframe(
                    pd.DataFrame([
                        {"Objetivo": f"{k[0]} · {k[1]}", "idLeague": v}
                        for k, v in sorted(get_tsdb_whitelist(tsdb_key).items(), key=lambda x: str(x[0]))
                    ]),
                    use_container_width=True,
                    hide_index=True,
                )
                st.write("**Eventos internacionales recibidos antes de aplicar la whitelist**")
                intl = [
                    {
                        "idEvent": e.get("idEvent"),
                        "idLeague": e.get("idLeague"),
                        "Competición API": e.get("strLeague"),
                        "Local": e.get("strHomeTeam"),
                        "Visitante": e.get("strAwayTeam"),
                        "Fecha API": e.get("dateEvent"),
                        "Hora API": e.get("strTime"),
                        "Estado": e.get("strStatus"),
                    }
                    for e in raw
                    if any(
                        word in str(e.get("strLeague") or "").lower()
                        for word in ("concacaf", "conmebol", "nations", "international", "world cup", "copa america")
                    )
                ]
                if intl:
                    st.dataframe(pd.DataFrame(intl), use_container_width=True, hide_index=True)
                else:
                    st.caption("No se detectaron eventos internacionales en la respuesta ya filtrada para esta fecha.")
            try:
                st.write("**Proveedor activo**")
                st.code(provider)
                if provider.startswith("TheSportsDB"):
                    st.write(f"Eventos recibidos antes del filtro de estado: {len(raw)}")
                    if raw:
                        st.json(raw[:3])
                st.write("**Mapeo de ligas**")
                st.json({f"{k[0]} · {k[1]}": v for k, v in league_mapping.items()})
                if league_errors:
                    st.write("**Errores**")
                    st.json({f"{k[0]} · {k[1]}": err for k, err in league_errors})
                if provider == "OpenFoot":
                    st.write("**Metadata consulta global (referencia)**")
                    st.json(get_match_meta(api_key, d.isoformat()))
            except Exception as e:
                st.error(f"No se pudo leer la metadata: {e}")
        risk_filter = st.multiselect(
            "Filtrar por riesgo",
            ["🟢 Muy bajo", "🟢 Bajo", "🟡 Medio", "🟠 Alto", "🔴 Muy alto", "⚪ Sin evaluar"],
            default=[],
            placeholder="Todos los niveles",
        )
        low_risk_only = st.toggle("Solo bajo riesgo", value=False)
        view = st.radio("Tanda", ["Todos", "Mañana", "Tarde", "Fuera de tandas"], horizontal=True)
        in_morning = df["_dt"].apply(lambda x: morning_start <= x.time() <= morning_end if pd.notna(x) else False)
        in_afternoon = df["_dt"].apply(lambda x: afternoon_start <= x.time() <= afternoon_end if pd.notna(x) else False)
        if view == "Mañana":
            shown = df[in_morning]
        elif view == "Tarde":
            shown = df[in_afternoon]
        elif view == "Fuera de tandas":
            shown = df[~(in_morning | in_afternoon)]
        else:
            shown = df
        if low_risk_only:
            shown = shown[shown["Riesgo"].isin(["🟢 Muy bajo", "🟢 Bajo"])]
        elif risk_filter:
            shown = shown[shown["Riesgo"].isin(risk_filter)]
        visible_cols = ["Hora CR", "Competición", "Partido", "0-0 Local", "0-0 Visit.", "Marca ≥1", "Recibe ≥1", "Casa/Fuera 0-0", "H2H 0-0", "P(+0.5) modelo", "Score +0.5", "Riesgo", "Cuota O0.5 ref.", "Rango cuota", "Estado"]
        st.dataframe(shown[visible_cols], use_container_width=True, hide_index=True)
        st.subheader("Experimento")
        st.caption("Guarda una fotografía prepartido de los análisis visibles. El resultado podrá completarse después sin cambiar el Score original.")
        if st.button("Guardar análisis visibles", type="primary"):
            saved = 0
            for _, erow in shown.iterrows():
                if erow["_fixture_id"] and erow["Score +0.5"] != "—":
                    save_experiment((
                        int(erow["_fixture_id"]), erow["_kickoff_raw"], erow["Competición"], erow["_home"], erow["_away"],
                        float(erow["Score +0.5"]), erow["Estado"], "Analizado", erow["Riesgo"], float(erow["_risk_score"]),
                        float(erow["_model_p_num"]) if erow["_model_p_num"] is not None else None,
                        erow["_home_zz"], erow["_home_n"], erow["_away_zz"], erow["_away_n"], "Pendiente"
                    ))
                    saved += 1
            st.success(f"{saved} evaluaciones prepartido guardadas.")
        st.subheader("Detalle de los datos usados")
        for _, row in shown.iterrows():
            with st.expander(str(row["Partido"]) + " · " + str(row["Estado"])):
                st.write("**Riesgo +0.5:** " + str(row["Riesgo"]) + " · índice de riesgo " + str(row["_risk_score"]) + "/100")
                if row["_risk_reasons"]:
                    st.write(" · ".join(row["_risk_reasons"]))
                left, right = st.columns(2)
                with left:
                    st.write("**Últimos resultados · local**")
                    if row["_home_scores"]:
                        st.write("\n".join("• " + x for x in row["_home_scores"]))
                    else:
                        st.caption("Sin histórico suficiente.")
                with right:
                    st.write("**Últimos resultados · visitante**")
                    if row["_away_scores"]:
                        st.write("\n".join("• " + x for x in row["_away_scores"]))
                    else:
                        st.caption("Sin histórico suficiente.")

elif page == "Experimento":
    ensure_experiment_schema()
    cols, saved_rows = evaluations()
    exp = pd.DataFrame(saved_rows, columns=cols)
    st.subheader("Experimento +0.5")
    if exp.empty:
        st.info("Todavía no hay evaluaciones guardadas. Usa 'Guardar análisis visibles' en el Radar.")
    else:
        completed = exp[exp["over05"].notna()] if "over05" in exp.columns else pd.DataFrame()
        a,b,c1,c2 = st.columns(4)
        a.metric("Evaluaciones", len(exp))
        b.metric("Finalizadas", len(completed))
        if not completed.empty:
            hits = int(completed["over05"].sum())
            c1.metric("+0.5", hits)
            c2.metric("Acierto observado", f"{100*hits/len(completed):.1f}%")
        else:
            c1.metric("+0.5", 0); c2.metric("Acierto observado", "—")
        show_cols=[x for x in ["kickoff","league","home","away","score","label","risk","risk_score","model_p","final_score","over05","result_status"] if x in exp.columns]
        st.dataframe(exp[show_cols], use_container_width=True, hide_index=True)
        if not completed.empty:
            st.subheader("Rendimiento por estado")
            perf=completed.groupby("label")["over05"].agg(["count","sum"]).reset_index()
            perf["Acierto %"]=(100*perf["sum"]/perf["count"]).round(1)
            perf.columns=["Estado","Partidos","+0.5","Acierto %"]
            st.dataframe(perf,use_container_width=True,hide_index=True)

elif page == "Historial":
    cols, rows = evaluations()
    df = pd.DataFrame(rows, columns=cols)
    if df.empty:
        st.info("Todavía no hay evaluaciones guardadas.")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)

else:
    st.subheader("Sistema +0.5 · migración OpenFoot")
    st.markdown("""
- El universo se limita a las 32 competiciones que seleccionamos manualmente.
- País y liga serán filtros de visualización, no una obligación de analizar una liga a la vez.
- El Radar final separará partidos antes/después de 12:45 PM Costa Rica.
- Solo calcularemos scores cuando exista histórico suficiente.
- El score seguirá siendo un índice experimental y no una probabilidad calibrada.
""")
