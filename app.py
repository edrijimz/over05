from __future__ import annotations
from datetime import date, datetime, time
from zoneinfo import ZoneInfo
import pandas as pd
import streamlit as st

from api_client import ApiFootball
from analysis_engine import summarize, rate
from database import evaluations
from config import TIMEZONE

st.set_page_config(page_title="Over 0.5 Analyzer", page_icon="⚽", layout="wide")
st.title("⚽ Over 0.5 Goal Analyzer")
st.caption("Análisis experimental de +0.5 goles. El score es un índice, no una probabilidad calibrada.")

with st.sidebar:
    st.header("Configuración")
    secret = st.secrets.get("API_FOOTBALL_KEY", "") if hasattr(st, "secrets") else ""
    api_key = st.text_input("API-Football key", value=secret, type="password")
    page = st.radio("Sección", ["Análisis por liga", "Historial", "Metodología"])

@st.cache_data(ttl=1800, show_spinner=False)
def get_fixtures(key, day):
    return ApiFootball(key).fixtures_by_date(day)

@st.cache_data(ttl=21600, show_spinner=False)
def recent_form(key, team_id, before_date):
    return ApiFootball(key).team_recent_free(team_id, before_date, limit=15)

@st.cache_data(ttl=21600, show_spinner=False)
def recent_h2h(key, home_id, away_id, before_date):
    return ApiFootball(key).h2h_free(home_id, away_id, before_date, limit=5)

def cr_time(iso):
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return dt.astimezone(ZoneInfo(TIMEZONE))

def pct(part, total):
    return round(100 * part / total) if total else 0

if page == "Análisis por liga":
    d = st.date_input("Fecha", date.today())
    if not api_key:
        st.info("Configura API_FOOTBALL_KEY en los Secrets de Streamlit.")
        st.stop()

    try:
        fixtures = get_fixtures(api_key, d.isoformat())
    except Exception as e:
        st.error(f"No se pudieron cargar los partidos: {e}")
        st.stop()

    if not fixtures:
        st.info("No se encontraron partidos para esta fecha.")
        st.stop()

    countries = sorted({f["league"].get("country") or "Otros" for f in fixtures})
    c1, c2, c3 = st.columns([1.2, 1.8, 1.2])
    country = c1.selectbox("País", ["Todos"] + countries)
    country_fixtures = fixtures if country == "Todos" else [f for f in fixtures if (f["league"].get("country") or "Otros") == country]

    leagues = sorted({(f["league"]["id"], f["league"]["name"]) for f in country_fixtures}, key=lambda x: x[1])
    league_names = ["Selecciona una liga"] + [name for _, name in leagues]
    league_name = c2.selectbox("Liga", league_names)
    cutoff = c3.time_input("Corte horario CR", time(12, 45))

    if league_name == "Selecciona una liga":
        st.info("Selecciona una liga. La app analizará automáticamente todos sus partidos de la fecha.")
        st.stop()

    league_id = next(i for i, n in leagues if n == league_name)
    selected = [f for f in country_fixtures if f["league"]["id"] == league_id]
    selected.sort(key=lambda f: cr_time(f["fixture"]["date"]))

    st.write(f"**{league_name} · {len(selected)} partido(s)**")
    st.caption("La primera carga consulta forma reciente y H2H; después se reutiliza caché para no gastar llamadas innecesarias.")

    rows = []
    progress = st.progress(0, text="Analizando liga…")
    for idx, f in enumerate(selected):
        home, away = f["teams"]["home"], f["teams"]["away"]
        match_date = f["fixture"]["date"][:10]
        try:
            hf = recent_form(api_key, home["id"], match_date)
            af = recent_form(api_key, away["id"], match_date)
            hs, aas = summarize(hf, home["id"]), summarize(af, away["id"])
            h2h = recent_h2h(api_key, home["id"], away["id"], match_date)
            h2h_zz = sum(1 for x in h2h if x.get("goals", {}).get("home") == 0 and x.get("goals", {}).get("away") == 0)
            score, label = rate(hs, aas, h2h_zz, len(h2h))
            kickoff = cr_time(f["fixture"]["date"])
            rows.append({
                "Hora CR": kickoff.strftime("%I:%M %p").lstrip("0"),
                "_dt": kickoff,
                "Tanda": "Antes 12:45" if kickoff.time() < cutoff else "Después 12:45",
                "Partido": f'{home["name"]} – {away["name"]}',
                "Score +0.5": score,
                "Estado": label,
                "0-0 Local últ.10": f'{sum(1 for x in hf[:10] if x.get("goals",{}).get("home")==0 and x.get("goals",{}).get("away")==0)}/{min(len(hf),10)}',
                "0-0 Visit. últ.10": f'{sum(1 for x in af[:10] if x.get("goals",{}).get("home")==0 and x.get("goals",{}).get("away")==0)}/{min(len(af),10)}',
                "Local marca ≥1": f"{pct(hs.scored, hs.matches)}%",
                "Visit. marca ≥1": f"{pct(aas.scored, aas.matches)}%",
                "Local recibe ≥1": f"{pct(hs.conceded, hs.matches)}%",
                "Visit. recibe ≥1": f"{pct(aas.conceded, aas.matches)}%",
                "H2H 0-0 últ.5": f"{h2h_zz}/{len(h2h)}",
            })
        except Exception as e:
            kickoff = cr_time(f["fixture"]["date"])
            rows.append({"Hora CR": kickoff.strftime("%I:%M %p").lstrip("0"), "_dt": kickoff, "Tanda": "Error", "Partido": f'{home["name"]} – {away["name"]}', "Score +0.5": None, "Estado": f"⚠️ {e}"})
        progress.progress((idx + 1) / len(selected), text=f"Analizando {idx+1}/{len(selected)}")

    progress.empty()
    df = pd.DataFrame(rows).sort_values("_dt")
    view = st.radio("Horario", ["Todos", "Antes del corte", "Después del corte"], horizontal=True)
    if view == "Antes del corte":
        df = df[df["_dt"].dt.time < cutoff]
    elif view == "Después del corte":
        df = df[df["_dt"].dt.time >= cutoff]

    order = st.selectbox("Ordenar por", ["Hora", "Score (mayor a menor)"])
    if order.startswith("Score"):
        df = df.sort_values("Score +0.5", ascending=False, na_position="last")
    else:
        df = df.sort_values("_dt")

    st.dataframe(df.drop(columns=["_dt"]), use_container_width=True, hide_index=True)

elif page == "Historial":
    cols, rows = evaluations()
    df = pd.DataFrame(rows, columns=cols)
    if df.empty:
        st.info("Todavía no hay evaluaciones guardadas.")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)
        resolved = df[df["zero_zero"].notna()]
        if not resolved.empty:
            st.metric("+0.5 observado", f'{100*(1-resolved["zero_zero"].mean()):.1f}%')

else:
    st.subheader("Sistema +0.5 v1.1")
    st.markdown("""
- Analiza automáticamente todos los partidos de la liga seleccionada.
- Los horarios se muestran en hora de Costa Rica y pueden dividirse antes/después de un corte configurable.
- Se muestran por separado los 0-0 recientes del local y del visitante.
- H2H 0-0 mide solamente los enfrentamientos directos y tiene peso secundario.
- El score prioriza forma reciente, frecuencia de marcar/recibir y ausencia de patrones 0-0.
- Un 0-0 aislado no descarta automáticamente un partido.
- El score es un índice experimental, no una probabilidad calibrada.
""")
