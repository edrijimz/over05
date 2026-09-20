from __future__ import annotations
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
import pandas as pd
import streamlit as st

from openfoot_client import OpenFoot
from database import evaluations
from config import TIMEZONE, TARGET_LEAGUES, KNOWN_COMPETITION_IDS

st.set_page_config(page_title="Over 0.5 Analyzer", page_icon="⚽", layout="wide")
st.title("⚽ Over 0.5 Goal Analyzer")
st.caption("Migración a OpenFoot · primero validamos cobertura antes de activar el radar completo.")

with st.sidebar:
    st.header("Configuración")
    api_key = st.secrets.get("OPENFOOT_API_KEY", "") if hasattr(st, "secrets") else ""
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

@st.cache_data(ttl=900, show_spinner=False)
def get_whitelist_matches(key, day):
    d = date.fromisoformat(day)
    api = OpenFoot(key)
    comps = api.competitions()
    mapping = resolve_competitions(comps)
    rows, errors = [], []
    # Query every resolved target competition on both UTC dates that can overlap the CR day.
    for target, cid in mapping.items():
        try:
            for utc_day in (d.isoformat(), (d + timedelta(days=1)).isoformat()):
                for m in api.matches_by_date(utc_day):
                    if m.get("competitionId") == cid and m.get("kickoffAt"):
                        if cr_time(m["kickoffAt"]).date() == d:
                            m["_target"] = target
                            rows.append(m)
        except Exception as e:
            errors.append((target, str(e)))
    unique = {m.get("id", f"{m.get('competitionId')}-{m.get('kickoffAt')}"): m for m in rows}
    return list(unique.values()), mapping, errors

if not api_key:
    st.error("Falta OPENFOOT_API_KEY en Streamlit Secrets.")
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
    d = st.date_input("Fecha", date.today())
    status_filter = st.selectbox("Estado", ["Próximos / en vivo", "Todos", "Finalizados"])
    morning_start, morning_end = time(3, 0), time(12, 0)
    afternoon_start, afternoon_end = time(12, 15), time(23, 30)
    try:
        matches, league_mapping, league_errors = get_whitelist_matches(api_key, d.isoformat())
    except Exception as e:
        st.error(f"No se pudieron cargar los partidos: {e}")
        st.stop()

    if status_filter == "Próximos / en vivo":
        matches = [m for m in matches if m.get("status") in {"scheduled", "live", "unknown"}]
    elif status_filter == "Finalizados":
        matches = [m for m in matches if m.get("status") == "finished"]

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
        st.info("OpenFoot no devolvió partidos para esta fecha.")
    else:
        df = pd.DataFrame(rows)
        df = df.sort_values("_dt", na_position="last")
        st.write(f"**{len(df)} partidos de nuestra whitelist para el día {d.isoformat()} en hora de Costa Rica**")
        st.caption(f"Ligas resueltas: {len(league_mapping)}/{len(TARGET_LEAGUES)}")
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
        with st.expander("Diagnóstico OpenFoot"):
            st.caption("Esto nos permite comprobar si la consulta global está paginada, limitada o tiene competiciones no disponibles.")
            try:
                st.write("**Mapeo de ligas**")
                st.json({f"{k[0]} · {k[1]}": v for k, v in league_mapping.items()})
                if league_errors:
                    st.write("**Errores**")
                    st.json({f"{k[0]} · {k[1]}": err for k, err in league_errors})
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
            shown = df[in_morning | in_afternoon]
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
