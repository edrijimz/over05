from __future__ import annotations
from datetime import date
import pandas as pd
import streamlit as st
from api_client import ApiFootball
from analysis_engine import summarize, rate
from database import save_evaluation, evaluations
from config import LOW_ODDS_THRESHOLD

st.set_page_config(page_title="Over 0.5 Analyzer", page_icon="⚽", layout="wide")
st.title("⚽ Over 0.5 Goal Analyzer")
st.caption("Sistema experimental de análisis. El score no es una probabilidad ni garantiza resultados.")

with st.sidebar:
    st.header("Configuración")
    secret = st.secrets.get("API_FOOTBALL_KEY", "") if hasattr(st, "secrets") else ""
    api_key=st.text_input("API-Football key", value=secret, type="password")
    page=st.radio("Sección", ["Próximos partidos","Historial","Metodología"])

if page=="Próximos partidos":
    d=st.date_input("Fecha", date.today())
    if not api_key:
        st.info("Agrega API_FOOTBALL_KEY en los Secrets de Streamlit o escribe la clave temporalmente aquí.")
        st.stop()
    api=ApiFootball(api_key)
    if st.button("Cargar y preanalizar", type="primary"):
        fixtures=api.fixtures_by_date(d.isoformat())
        st.session_state["fixtures"]=fixtures
    fixtures=st.session_state.get("fixtures",[])
    if fixtures:
        st.write(f"{len(fixtures)} partidos encontrados. Selecciona candidatos para análisis profundo.")
        options={f'{x["league"]["name"]}: {x["teams"]["home"]["name"]} vs {x["teams"]["away"]["name"]}':x for x in fixtures}
        picked=st.multiselect("Partidos", list(options))
        for name in picked:
            f=options[name]; home=f["teams"]["home"]; away=f["teams"]["away"]
            with st.expander(name, expanded=True):
                try:
                    hf=api.team_last(home["id"],15); af=api.team_last(away["id"],15)
                    hs=summarize(hf,home["id"]); aas=summarize(af,away["id"])
                    h2h=api.h2h(home["id"],away["id"],5)
                    zz=sum(1 for x in h2h if x.get("goals",{}).get("home")==0 and x.get("goals",{}).get("away")==0)
                    score,label=rate(hs,aas,zz,len(h2h))
                    c1,c2,c3=st.columns(3); c1.metric("Score",f"{score}/100"); c2.metric("Clasificación",label); c3.metric("H2H 0-0",f"{zz}/{len(h2h)}")
                    st.write({"Local últimos":hs.__dict__,"Visitante últimos":aas.__dict__})
                    odds=st.number_input("Cuota +0.5 (opcional)",min_value=1.0,value=1.02,step=0.01,key=f'o{f["fixture"]["id"]}')
                    auto="🔵 Aprobado / cuota baja" if score>=78 and odds<LOW_ODDS_THRESHOLD else ("🟢 Candidato" if score>=78 else "🔴 No seleccionar")
                    decision=st.selectbox("Decisión",[auto,"🟢 Candidato","🔵 Aprobado / cuota baja","🟡 Revisar","🔴 Descartado"],key=f'd{f["fixture"]["id"]}')
                    if st.button("Guardar evaluación",key=f's{f["fixture"]["id"]}'):
                        save_evaluation((f["fixture"]["id"],f["fixture"]["date"],f["league"]["name"],home["name"],away["name"],score,label,odds,decision,None,None,None)); st.success("Guardado")
                except Exception as e: st.error(f"No se pudo analizar: {e}")

elif page=="Historial":
    cols,rows=evaluations(); df=pd.DataFrame(rows,columns=cols)
    if df.empty: st.info("Todavía no hay evaluaciones guardadas.")
    else:
        st.dataframe(df,use_container_width=True,hide_index=True)
        resolved=df[df["zero_zero"].notna()]
        if not resolved.empty:
            st.metric("+0.5 observado",f'{100*(1-resolved["zero_zero"].mean()):.1f}%')

else:
    st.subheader("Sistema +0.5 v1.0")
    st.markdown("""
- Prioriza ausencia de patrones 0-0 en los últimos 10–15 partidos.
- Evalúa frecuencia de marcar y conceder de ambos equipos.
- H2H es secundario, no decisivo por sí solo.
- Un 0-0 aislado no descarta automáticamente un candidato.
- Un equipo capaz de cubrir el único gol por sí mismo mejora el perfil.
- La cuota se revisa después del análisis deportivo; nunca se agregan mercados para alcanzar una cuota objetivo.
- Los candidatos excelentes con cuota menor a 1.02 se registran como 🔵 para estudiar su desempeño sin necesidad de seleccionarlos.
- El score es un índice experimental, no una probabilidad calibrada.
""")
