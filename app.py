
import os
import sqlite3
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Traffic Quest", page_icon="🕹️", layout="wide")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "traffic.db")
os.makedirs(DATA_DIR, exist_ok=True)

QUEST_TYPES = {
    "BAU / Always-On": 1.0,
    "Campaign / Launch": 1.15,
    "Pitch": 1.35,
    "Awards Case / Effies": 1.25,
    "Research / Foresight": 1.05,
    "Crisis / Rush": 1.5,
}
PRIORITY_MULT = {"Low": 0.75, "Medium": 1.0, "High": 1.25, "Critical": 1.5}

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Press+Start+2P&display=swap');
html, body, [class*="css"] {font-family: 'Press Start 2P', monospace !important;}
.stApp {background: radial-gradient(circle at 20% 20%, #101a3a 0%, #0b1020 55%, #070a14 100%) !important; color: #e6f0ff;}
.block {border: 2px solid #2a3a66; background: linear-gradient(180deg, #111a33 0%, #0f1730 100%); padding: 12px; border-radius: 10px; margin-bottom: 10px;}
</style>
""", unsafe_allow_html=True)

def conn():
    os.makedirs(DATA_DIR, exist_ok=True)
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    c = conn()
    cur = c.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS planners(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            weekly_capacity INTEGER NOT NULL DEFAULT 40,
            active INTEGER NOT NULL DEFAULT 1
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS projects(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            client TEXT,
            brief TEXT,
            status TEXT NOT NULL DEFAULT 'Active',
            quest_type TEXT NOT NULL DEFAULT 'BAU / Always-On',
            priority TEXT NOT NULL DEFAULT 'Medium',
            effort_xp INTEGER NOT NULL DEFAULT 8,
            start_date TEXT,
            due_date TEXT,
            lead_planner TEXT,
            support_planner TEXT,
            created_at TEXT NOT NULL
        )
    """)
    c.commit()
    c.close()

def seed():
    c = conn()
    cur = c.cursor()
    cur.execute("SELECT COUNT(*) FROM planners")
    if cur.fetchone()[0] == 0:
        cur.executemany(
            "INSERT INTO planners(name, weekly_capacity, active) VALUES (?, ?, 1)",
            [("Merc", 40), ("Phyllis", 40), ("Fritz", 40), ("Nanais", 45)]
        )
        c.commit()
    c.close()

def planners_df(active_only=False):
    c = conn()
    q = "SELECT name, weekly_capacity, active FROM planners"
    if active_only:
        q += " WHERE active=1"
    df = pd.read_sql_query(q + " ORDER BY name", c)
    c.close()
    return df

def projects_df():
    c = conn()
    df = pd.read_sql_query("SELECT * FROM projects ORDER BY due_date IS NULL, due_date ASC, created_at DESC", c)
    c.close()
    return df

def adjusted_xp(xp, priority, quest_type):
    return round(float(xp) * PRIORITY_MULT.get(priority, 1.0) * QUEST_TYPES.get(quest_type, 1.0), 1)

def compute_load(planners, projects):
    p = planners.copy()
    active = projects[projects["status"] == "Active"].copy()
    loads = {n: 0.0 for n in p["name"].tolist()}
    for _, r in active.iterrows():
        axp = adjusted_xp(r["effort_xp"], r["priority"], r["quest_type"])
        lead = r["lead_planner"]
        support = r["support_planner"]
        if lead in loads:
            loads[lead] += axp * 0.7
        if support in loads and pd.notna(support) and support != lead:
            loads[support] += axp * 0.3
    p["load_xp"] = p["name"].map(lambda n: round(loads.get(n, 0.0), 1))
    p["load_pct"] = p.apply(lambda r: round((r["load_xp"] / r["weekly_capacity"]) * 100, 1) if r["weekly_capacity"] else 0, axis=1)
    def state(x):
        if x >= 110: return "OVERLOADED"
        if x >= 90: return "FULL"
        if x >= 70: return "BUSY"
        return "OK"
    p["state"] = p["load_pct"].map(state)
    return p

def suggest_assignment(planners, projects, xp, priority, qtype):
    base = compute_load(planners, projects)
    caps = {r["name"]: r["weekly_capacity"] for _, r in planners.iterrows()}
    current = {r["name"]: r["load_xp"] for _, r in base.iterrows()}
    names = planners["name"].tolist()
    axp = adjusted_xp(xp, priority, qtype)
    best = None
    best_score = None
    for lead in names:
        for support in ["—"] + names:
            temp = current.copy()
            temp[lead] += axp * 0.7
            if support != "—" and support != lead:
                temp[support] += axp * 0.3
            pcts = [(temp[n] / caps[n]) * 100 for n in names]
            score = (max(pcts), sum(pcts))
            if best_score is None or score < best_score:
                best_score = score
                best = (lead, support)
    return best, round(best_score[0], 1)

def add_project(title, client, brief, status, qtype, priority, xp, start, due, lead, support):
    c = conn()
    cur = c.cursor()
    cur.execute(
        """INSERT INTO projects(title, client, brief, status, quest_type, priority, effort_xp, start_date, due_date, lead_planner, support_planner, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (title, client, brief, status, qtype, priority, int(xp), start, due, lead, None if support == "—" else support, datetime.now().isoformat(timespec="seconds"))
    )
    c.commit()
    c.close()

def upsert_planner(name, capacity, active):
    c = conn()
    cur = c.cursor()
    cur.execute("SELECT id FROM planners WHERE name=?", (name,))
    row = cur.fetchone()
    if row:
        cur.execute("UPDATE planners SET weekly_capacity=?, active=? WHERE name=?", (capacity, active, name))
    else:
        cur.execute("INSERT INTO planners(name, weekly_capacity, active) VALUES (?, ?, ?)", (name, capacity, active))
    c.commit()
    c.close()

def week_start(d):
    return d - timedelta(days=d.weekday())

def weekly_grid(planners, projects, weeks=8):
    start = week_start(date.today())
    cols = [(start + timedelta(days=7*i)) for i in range(weeks)]
    grid = pd.DataFrame(0.0, index=planners["name"].tolist(), columns=[c.isoformat() for c in cols])
    active = projects[projects["status"] == "Active"].copy()
    for _, r in active.iterrows():
        anchor = r["due_date"] or r["start_date"]
        try:
            dt = datetime.fromisoformat(anchor).date() if anchor else date.today()
        except Exception:
            dt = date.today()
        ws = week_start(dt)
        key = ws.isoformat()
        if key not in grid.columns:
            continue
        axp = adjusted_xp(r["effort_xp"], r["priority"], r["quest_type"])
        lead = r["lead_planner"]
        support = r["support_planner"]
        if lead in grid.index:
            grid.loc[lead, key] += axp * 0.7
        if support in grid.index and pd.notna(support) and support != lead:
            grid.loc[support, key] += axp * 0.3
    return grid.round(1), cols

init_db()
seed()

st.markdown('<div class="block"><h3>🕹️ Traffic Quest: Strategy Guild Board</h3><p>Manage briefs like quests. Assign heroes. Avoid overload.</p></div>', unsafe_allow_html=True)

page = st.sidebar.radio("NAV MENU", ["Dashboard", "Add Quest", "Quest Log", "Dungeon Weeks", "Guild Settings"])

pl = planners_df()
active_pl = planners_df(active_only=True)
pr = projects_df()

if page == "Dashboard":
    load = compute_load(active_pl[["name", "weekly_capacity"]], pr)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Active", int((pr["status"] == "Active").sum()) if not pr.empty else 0)
    c2.metric("On Hold", int((pr["status"] == "On Hold").sum()) if not pr.empty else 0)
    c3.metric("Done", int((pr["status"] == "Done").sum()) if not pr.empty else 0)
    c4.metric("Risk", int(load["state"].isin(["FULL", "OVERLOADED"]).sum()))
    st.subheader("Team Load")
    st.dataframe(load, use_container_width=True, hide_index=True)
    st.subheader("Projects")
    st.dataframe(pr, use_container_width=True, hide_index=True)

elif page == "Add Quest":
    st.subheader("New Quest")
    title = st.text_input("Project")
    client = st.text_input("Client")
    brief = st.text_area("Brief")
    col1, col2, col3 = st.columns(3)
    with col1:
        qtype = st.selectbox("Quest Type", list(QUEST_TYPES.keys()))
    with col2:
        priority = st.selectbox("Priority", list(PRIORITY_MULT.keys()), index=1)
    with col3:
        xp = st.number_input("Base XP", 1, 100, 8)
    st.caption(f"Adjusted XP: {adjusted_xp(xp, priority, qtype)}")
    col4, col5, col6 = st.columns(3)
    with col4:
        status = st.selectbox("Status", ["Active", "On Hold", "Done"])
    with col5:
        start = st.date_input("Start Date", value=date.today())
    with col6:
        due = st.date_input("Due Date", value=None)

    if st.button("Auto-suggest assignments"):
        pair, max_pct = suggest_assignment(active_pl[["name", "weekly_capacity"]], pr, xp, priority, qtype)
        st.session_state["lead"] = pair[0]
        st.session_state["support"] = pair[1]
        st.success(f"Suggested lead: {pair[0]} | support: {pair[1]} | projected max load: {max_pct}%")

    lead_default = st.session_state.get("lead", active_pl["name"].tolist()[0] if not active_pl.empty else None)
    support_default = st.session_state.get("support", "—")
    col7, col8 = st.columns(2)
    with col7:
        lead = st.selectbox("Lead Planner", active_pl["name"].tolist(), index=active_pl["name"].tolist().index(lead_default) if lead_default in active_pl["name"].tolist() else 0)
    with col8:
        support_choices = ["—"] + active_pl["name"].tolist()
        support = st.selectbox("Support Planner", support_choices, index=support_choices.index(support_default) if support_default in support_choices else 0)

    if st.button("Save Quest"):
        if not title.strip():
            st.error("Project title is required.")
        else:
            add_project(
                title.strip(), client.strip(), brief.strip(), status, qtype, priority, xp,
                start.isoformat() if start else None,
                due.isoformat() if due else None,
                lead, support
            )
            st.success("Quest saved.")
            st.rerun()

elif page == "Quest Log":
    st.subheader("Quest Log")
    st.dataframe(pr, use_container_width=True, hide_index=True)

elif page == "Dungeon Weeks":
    st.subheader("Dungeon Weeks")
    weeks = st.number_input("Weeks", 4, 16, 8)
    grid, week_cols = weekly_grid(active_pl[["name", "weekly_capacity"]], pr, int(weeks))
    caps = active_pl.set_index("name")["weekly_capacity"].to_dict()
    display = pd.DataFrame(index=grid.index)
    for d in week_cols:
        key = d.isoformat()
        label = d.strftime("Wk of %b %d")
        display[label] = [f"{grid.loc[name, key]:.1f}xp ({(grid.loc[name, key]/caps[name]*100 if caps[name] else 0):.1f}%)" for name in grid.index]
    st.dataframe(display, use_container_width=True)

elif page == "Guild Settings":
    st.subheader("Planners")
    st.dataframe(pl, use_container_width=True, hide_index=True)
    name = st.text_input("Planner Name")
    capacity = st.number_input("Weekly Capacity", 5, 100, 40)
    active = st.checkbox("Active", True)
    if st.button("Save Planner"):
        if name.strip():
            upsert_planner(name.strip(), int(capacity), 1 if active else 0)
            st.success("Planner saved.")
            st.rerun()
        else:
            st.error("Planner name is required.")
