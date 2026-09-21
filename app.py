from __future__ import annotations
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
import pandas as pd
import streamlit as st

from openfoot_client import OpenFoot
from thesportsdb_client import TheSportsDB
from database import evaluations
from config import TIMEZONE, TARGET_LEAGUES, KNOWN_COMPETITION_IDS, TSDB_TARGET_ALIASES, TSDB_EXTRA_COMPETITION_ALIASES, TSDB_KNOWN_LEAGUE_IDS

st.set_page_config(page_title="Over 0.5 Analyzer", page_icon="⚽", layout="wide")
st.title("⚽ Over 0.5 Goal Analyzer")
st.caption("TheSportsDB Premium · horarios mostrados en hora de Costa Rica (UTC−6).")

with st.sidebar:
    st.header("Configuración")
    api_key = st.secrets.get("OPENFOOT_API_KEY", "") if hasattr(st, "secrets") else ""
    tsdb_key = st.secrets.get("THESPORTSDB_API_KEY", "123") if hasattr(st, "secrets") else "123"
    page = st.radio("Sección", ["Radar", "Cobertura", "Historial", "Metodología"])

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

            # Premium Schedule Day can return up to 1500 events, so two bulk
            # requests are enough for one Costa Rica calendar day (which spans
            # parts of two UTC dates). Filtering per league here would create
            # 60+ requests per refresh and can trigger HTTP 429.
            raw_all = (
                api_tsdb.events_day(d.isoformat(), "Soccer")
                + api_tsdb.events_day((d + timedelta(days=1)).isoformat(), "Soccer")
            )
            raw_all = list({str(e.get("idEvent")): e for e in raw_all if e.get("idEvent")}.values())
            international_terms = (
                "concacaf", "conmebol", "nations league", "copa america",
                "world cup qualifying", "international friendlies"
            )
            raw = [
                e for e in raw_all
                if str(e.get("idLeague") or "") in allowed_ids
                or any(term in str(e.get("strLeague") or "").lower() for term in international_terms)
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
                    "kickoffAt": kickoff,
                    "competitionName": e.get("strLeague") or "",
                    "competitionId": e.get("idLeague") or "",
                    "homeTeam": {"name": e.get("strHomeTeam") or ""},
                    "awayTeam": {"name": e.get("strAwayTeam") or ""},
                    "status": status,
                })
        else:
            matches, league_mapping, league_errors = get_whitelist_matches(api_key, d.isoformat())
    except Exception as e:
        st.error(f"No se pudieron cargar los partidos: {e}")
        st.stop()

    # El Radar solo muestra partidos que todavía no comenzaron.
    matches = [m for m in matches if m.get("status") == "scheduled"]

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
        rows.append({
            "Hora CR": kickoff.strftime("%I:%M %p").lstrip("0") if kickoff else "",
            "_dt": kickoff,
            "Competición": comp_name,
            "Partido": f'{home.get("name","")} – {away.get("name","")}',
            "Estado API": m.get("status", ""),
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
            st.caption(f"TheSportsDB Premium · whitelist activa · {len(get_tsdb_whitelist(tsdb_key))} competiciones resueltas")
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
        st.warning("Radar en modo de validación: todavía no asignamos Score +0.5 hasta fijar los IDs de nuestras ligas y cargar históricos.")
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
        st.dataframe(shown.drop(columns=["_dt"]), use_container_width=True, hide_index=True)

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
