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
