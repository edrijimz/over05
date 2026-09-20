# Over 0.5 Goal Analyzer

Aplicación Streamlit para registrar y evaluar de forma reproducible el experimento de partidos con **más de 0.5 goles**.

## Funciones iniciales
- Descarga fixtures desde API-Football.
- Obtiene últimos 15 partidos por equipo y H2H.
- Calcula un score experimental para evitar 0-0.
- Semáforo 🟢🟢 / 🟢 / 🟡 / 🔴 y categoría 🔵 para cuotas muy bajas.
- Guarda evaluaciones antes del partido en SQLite.
- Historial para comparar posteriormente el filtro con resultados reales.

## Ejecutar localmente
1. Python 3.11+.
2. `pip install -r requirements.txt`
3. Crea `.streamlit/secrets.toml`:
   ```toml
   API_FOOTBALL_KEY = "TU_CLAVE"
   ```
4. `streamlit run app.py`

## Streamlit Community Cloud
Conecta este repositorio, selecciona `app.py` y agrega `API_FOOTBALL_KEY` en **App settings → Secrets**. Nunca publiques la clave en GitHub.

## Nota metodológica
El score v1.0 es un índice heurístico y no una probabilidad. Las reglas deben congelarse durante una muestra y evaluarse fuera de muestra antes de ajustar pesos. La aplicación no automatiza apuestas.
