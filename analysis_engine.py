from __future__ import annotations
from dataclasses import dataclass

@dataclass
class TeamForm:
    matches: int
    zero_zero: int
    scored: int
    conceded: int
    avg_total_goals: float
    scores: tuple = ()


def summarize(fixtures: list, team_id: int) -> TeamForm:
    zz=scored=conceded=0; totals=[]
    for f in fixtures:
        g=f.get("goals", {}); h=g.get("home"); a=g.get("away")
        if h is None or a is None: continue
        home=f["teams"]["home"]["id"] == team_id
        gf, ga=(h,a) if home else (a,h)
        zz += int(h == 0 and a == 0)
        scored += int(gf > 0); conceded += int(ga > 0); totals.append(h+a)
    n=len(totals)
    return TeamForm(n,zz,scored,conceded,sum(totals)/n if n else 0)


def rate(home: TeamForm, away: TeamForm, h2h_zero_zero: int=0, h2h_n: int=0):
    # Score estimates suitability for avoiding 0-0; it is NOT a calibrated probability.
    n=max(home.matches+away.matches,1)
    zz_rate=(home.zero_zero+away.zero_zero)/n
    scoring=(home.scored+away.scored)/n
    conceding=(home.conceded+away.conceded)/n
    score=35*(1-min(zz_rate/0.25,1)) + 25*scoring + 20*conceding
    score += 10*min((home.avg_total_goals+away.avg_total_goals)/5,1)
    if h2h_n: score += 5*(1-h2h_zero_zero/h2h_n)
    score += 5*max(home.scored/max(home.matches,1), away.scored/max(away.matches,1))
    score=max(0,min(round(score,1),100))
    if score >= 88: label="🟢🟢 Muy fuerte"
    elif score >= 78: label="🟢 Fuerte"
    elif score >= 65: label="🟡 Revisar"
    else: label="🔴 Descartar"
    return score,label


def summarize_tsdb(events: list, team_id: str, limit: int = 10) -> TeamForm:
    rows = []
    for e in events:
        try:
            hg, ag = int(e.get("intHomeScore")), int(e.get("intAwayScore"))
        except (TypeError, ValueError):
            continue
        if str(team_id) not in {str(e.get("idHomeTeam") or ""), str(e.get("idAwayTeam") or "")}:
            continue
        rows.append((e, hg, ag))
    rows = rows[:limit]
    zz = scored = conceded = 0
    totals, scorelines = [], []
    for e, hg, ag in rows:
        is_home = str(e.get("idHomeTeam") or "") == str(team_id)
        gf, ga = (hg, ag) if is_home else (ag, hg)
        zz += int(hg == 0 and ag == 0)
        scored += int(gf > 0)
        conceded += int(ga > 0)
        totals.append(hg + ag)
        scorelines.append(str(e.get("strHomeTeam") or "") + " " + str(hg) + "-" + str(ag) + " " + str(e.get("strAwayTeam") or ""))
    n = len(rows)
    return TeamForm(n, zz, scored, conceded, sum(totals) / n if n else 0, tuple(scorelines))


def venue_split_tsdb(events: list, team_id: str, venue: str, limit: int = 10) -> TeamForm:
    wanted_home = venue == "home"
    filtered = []
    for e in events:
        is_home = str(e.get("idHomeTeam") or "") == str(team_id)
        is_away = str(e.get("idAwayTeam") or "") == str(team_id)
        if (wanted_home and is_home) or ((not wanted_home) and is_away):
            filtered.append(e)
    return summarize_tsdb(filtered, team_id, limit)


def summarize_h2h_tsdb(events: list, limit: int = 5):
    valid = []
    for e in events:
        try:
            hg, ag = int(e.get("intHomeScore")), int(e.get("intAwayScore"))
        except (TypeError, ValueError):
            continue
        valid.append((hg, ag))
        if len(valid) >= limit:
            break
    return len(valid), sum(1 for hg, ag in valid if hg == 0 and ag == 0)


def poisson_over05(home: TeamForm, away: TeamForm):
    import math
    if home.matches < 5 or away.matches < 5:
        return None
    lam = (home.avg_total_goals + away.avg_total_goals) / 2
    return round((1 - math.exp(-lam)) * 100, 1)


def risk_level(home: TeamForm, away: TeamForm, home_venue: TeamForm | None = None, away_venue: TeamForm | None = None, h2h_zero_zero: int = 0, h2h_n: int = 0):
    # Risk answers one narrow question: how much evidence points to a 0-0?
    # A team failing to score is not itself dangerous if the opponent regularly scores.
    if home.matches < 5 or away.matches < 5:
        return "⚪ Sin evaluar", 0, ["Histórico insuficiente"]

    risk = 0.0
    reasons = []
    n = home.matches + away.matches
    zz = home.zero_zero + away.zero_zero
    zz_rate = zz / n

    # 1) Actual 0-0 frequency is the strongest signal.
    risk += min(48, zz_rate * 160)
    if zz == 0:
        reasons.append("Sin 0-0 recientes en la forma general")
    elif zz <= 2:
        reasons.append("Frecuencia reciente de 0-0 baja")
    else:
        reasons.append("Patrón reciente de 0-0 a vigilar")

    # 2) One-team coverage: for O0.5, one reliable scorer can be enough.
    home_cover = home.scored / home.matches
    away_cover = away.scored / away.matches
    best_cover = max(home_cover, away_cover)
    combined_failure = (1 - home_cover) * (1 - away_cover)
    risk += combined_failure * 30

    if best_cover >= 0.9:
        risk -= 14
        reasons.append("Un equipo marcó en ≥90% y puede cubrir el gol")
    elif best_cover >= 0.8:
        risk -= 9
        reasons.append("Un equipo marcó en ≥80% y ofrece buena cobertura")
    elif best_cover < 0.7:
        risk += 8
        reasons.append("Ningún equipo supera 70% de partidos marcando")

    # 3) Conceding supports the opposite route to the required single goal.
    best_concede = max(home.conceded / home.matches, away.conceded / away.matches)
    if best_concede >= 0.8:
        risk -= 7
        reasons.append("Al menos un equipo recibió gol en ≥80%")
    elif best_concede < 0.5:
        risk += 6
        reasons.append("Ambos muestran baja frecuencia de recibir gol")

    # 4) Venue split matters, but does not duplicate the general sample heavily.
    if home_venue and away_venue:
        venue_n = home_venue.matches + away_venue.matches
        if venue_n >= 6:
            venue_zz = home_venue.zero_zero + away_venue.zero_zero
            venue_rate = venue_zz / venue_n
            risk += min(12, venue_rate * 45)
            if venue_zz == 0:
                reasons.append("Sin 0-0 en la muestra casa/fuera")
            elif venue_rate >= 0.2:
                reasons.append("Casa/fuera añade señal de 0-0")

    # 5) H2H is deliberately secondary.
    if h2h_n >= 3:
        h2h_rate = h2h_zero_zero / h2h_n
        risk += min(6, h2h_rate * 12)
        if h2h_zero_zero >= 2:
            reasons.append("H2H repite 0-0, con peso secundario")

    risk = max(0, min(round(risk), 100))
    if risk <= 10:
        label = "🟢 Muy bajo"
    elif risk <= 22:
        label = "🟢 Bajo"
    elif risk <= 38:
        label = "🟡 Medio"
    elif risk <= 55:
        label = "🟠 Alto"
    else:
        label = "🔴 Muy alto"
    return label, risk, reasons
