from __future__ import annotations
import sqlite3
from pathlib import Path
DB=Path("over05.db")

def connect():
    c=sqlite3.connect(DB)
    c.execute("""CREATE TABLE IF NOT EXISTS evaluations(
      id INTEGER PRIMARY KEY, fixture_id INTEGER UNIQUE, kickoff TEXT, league TEXT,
      home TEXT, away TEXT, score REAL, label TEXT, odds REAL, decision TEXT,
      home_goals INTEGER, away_goals INTEGER, zero_zero INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("""CREATE TABLE IF NOT EXISTS bets(
      id INTEGER PRIMARY KEY, placed_at TEXT DEFAULT CURRENT_TIMESTAMP, session TEXT,
      stake REAL, combined_odds REAL, return_amount REAL, status TEXT, notes TEXT)""")
    c.commit(); return c

def save_evaluation(row):
    c=connect(); c.execute("""INSERT OR REPLACE INTO evaluations
    (fixture_id,kickoff,league,home,away,score,label,odds,decision,home_goals,away_goals,zero_zero)
    VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""", row); c.commit(); c.close()

def evaluations():
    c=connect(); rows=c.execute("SELECT * FROM evaluations ORDER BY kickoff DESC").fetchall(); cols=[d[0] for d in c.execute("SELECT * FROM evaluations LIMIT 0").description]; c.close(); return cols,rows


def ensure_experiment_schema():
    c=connect()
    existing={r[1] for r in c.execute("PRAGMA table_info(evaluations)").fetchall()}
    additions={
      "risk":"TEXT","risk_score":"REAL","model_p":"REAL","home_zero_zero":"INTEGER",
      "home_n":"INTEGER","away_zero_zero":"INTEGER","away_n":"INTEGER",
      "result_status":"TEXT","final_score":"TEXT","over05":"INTEGER","updated_at":"TEXT"
    }
    for name, typ in additions.items():
        if name not in existing:
            c.execute("ALTER TABLE evaluations ADD COLUMN " + name + " " + typ)
    c.commit(); c.close()

def save_experiment(row):
    ensure_experiment_schema()
    c=connect()
    c.execute("""INSERT INTO evaluations
      (fixture_id,kickoff,league,home,away,score,label,decision,risk,risk_score,model_p,
       home_zero_zero,home_n,away_zero_zero,away_n,result_status)
      VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
      ON CONFLICT(fixture_id) DO UPDATE SET
       kickoff=excluded.kickoff,league=excluded.league,home=excluded.home,away=excluded.away,
       score=excluded.score,label=excluded.label,decision=excluded.decision,risk=excluded.risk,
       risk_score=excluded.risk_score,model_p=excluded.model_p,home_zero_zero=excluded.home_zero_zero,
       home_n=excluded.home_n,away_zero_zero=excluded.away_zero_zero,away_n=excluded.away_n""", row)
    c.commit(); c.close()

def update_result(fixture_id, home_goals, away_goals):
    ensure_experiment_schema()
    c=connect()
    total=int(home_goals)+int(away_goals)
    c.execute("""UPDATE evaluations SET home_goals=?,away_goals=?,zero_zero=?,final_score=?,
      over05=?,result_status='Finalizado',updated_at=CURRENT_TIMESTAMP WHERE fixture_id=?""",
      (home_goals,away_goals,int(total==0),f"{home_goals}-{away_goals}",int(total>0),fixture_id))
    c.commit(); c.close()
