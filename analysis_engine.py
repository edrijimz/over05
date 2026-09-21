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
