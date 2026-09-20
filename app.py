from __future__ import annotations
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
import pandas as pd
import streamlit as st

from openfoot_client import OpenFoot
from database import evaluations
from config import TIMEZONE, TARGET_LEAGUES

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
    cutoff = st.time_input("Corte horario CR", time(12, 45))
    status_filter = st.selectbox("Estado", ["Próximos / en vivo", "Todos", "Finalizados"])
    try:
        matches = get_matches_cr_day(api_key, d.isoformat())
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
        st.write(f"**{len(df)} partidos para el día {d.isoformat()} en hora de Costa Rica**")
        before = int(sum(x.time() < cutoff for x in df["_dt"] if pd.notna(x)))
        after = int(sum(x.time() >= cutoff for x in df["_dt"] if pd.notna(x)))
        a, b, c = st.columns(3)
        a.metric("Mostrados", len(df))
        b.metric("Antes del corte", before)
        c.metric("Desde 12:45 PM", after)
        st.warning("Radar en modo de validación: todavía no asignamos Score +0.5 hasta fijar los IDs de nuestras ligas y cargar históricos.")
        view = st.radio("Tanda", ["Todos", "Antes de 12:45", "Desde 12:45"], horizontal=True)
        shown = df
        if view == "Antes de 12:45":
            shown = df[df["_dt"].apply(lambda x: x.time() < cutoff if pd.notna(x) else False)]
        elif view == "Desde 12:45":
            shown = df[df["_dt"].apply(lambda x: x.time() >= cutoff if pd.notna(x) else False)]
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
