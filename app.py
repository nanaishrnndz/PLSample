
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
    "BAU": 1.0,
    "Campaign": 1.15,
    "Pitch": 1.35,
    "Awards": 1.25,
    "Research": 1.05,
    "Rush": 1.5,
}
PRIORITY_MULT = {"Low": 0.75, "Medium": 1.0, "High": 1.25, "Critical": 1.5}

RETRO_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Press+Start+2P&display=swap');

html, body, [data-testid="stAppViewContainer"], [data-testid="stSidebar"], .stApp, * {
    font-family: 'Press Start 2P', monospace !important;
}

.stApp {
    background: radial-gradient(circle at 20% 20%, #101a3a 0%, #0b1020 55%, #070a14 100%) !important;
    color: white !important;
}

.block {
    border: 2px solid #2a3a66;
    background: linear-gradient(180deg, #111a33 0%, #0f1730 100%);
    padding: 12px;
    border-radius: 10px;
    margin-bottom: 14px;
    box-shadow: 0 8px 0 rgba(0,0,0,0.30);
}

.metric-card {
    border: 2px solid #2a3a66;
    background: linear-gradient(180deg, #111a33 0%, #0f1730 100%);
    padding: 16px;
    border-radius: 10px;
    text-align: center;
    margin-bottom: 12px;
}

.metric-label {
    font-size: 12px;
    margin-bottom: 10px;
}

.metric-value {
    font-size: 26px;
}

.green { color: #4cff4c; }
.yellow { color: #ffd84c; }
.blue { color: #66ccff; }
.red { color: #ff4c4c; }

div[data-testid="stDataFrame"] * {
    font-family: 'Press Start 2P', monospace !important;
}
</style>
"""
st.markdown(RETRO_CSS, unsafe_allow_html=True)

def conn():
    os.makedirs(DATA_DIR, exist_ok=True)
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def table_columns(connection, table_name):
    cur = connection.cursor()
    cur.execute(f"PRAGMA table_info({table_name})")
    return [row[1] for row in cur.fetchall()]

def ensure_column(connection, table_name, column_name, ddl):
    cols = table_columns(connection, table_name)
    if column_name not in cols:
        cur = connection.cursor()
        cur.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}")
        connection.commit()

def init_db():
    c = conn()
    cur = c.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS planners(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            weekly_capacity INTEGER DEFAULT 40,
            active INTEGER DEFAULT 1
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS projects(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            client TEXT,
            brief TEXT,
            status TEXT DEFAULT 'Active',
            quest_type TEXT DEFAULT 'BAU',
            priority TEXT DEFAULT 'Medium',
            effort_xp INTEGER DEFAULT 8,
            start_date TEXT,
            due_date TEXT,
            lead TEXT,
            support TEXT,
            created_at TEXT
        )
    """)

    # Migrate older schemas safely
    ensure_column(c, "projects", "status", "TEXT DEFAULT 'Active'")
    ensure_column(c, "projects", "quest_type", "TEXT DEFAULT 'BAU'")
    ensure_column(c, "projects", "priority", "TEXT DEFAULT 'Medium'")
    ensure_column(c, "projects", "effort_xp", "INTEGER DEFAULT 8'")
    ensure_column(c, "projects", "start_date", "TEXT")
    ensure_column(c, "projects", "due_date", "TEXT")
    ensure_column(c, "projects", "lead", "TEXT")
    ensure_column(c, "projects", "support", "TEXT")
    ensure_column(c, "projects", "created_at", "TEXT")

    cols = table_columns(c, "projects")
    cur = c.cursor()
    # Map from old names if present
    if "lead_planner" in cols:
        cur.execute("UPDATE projects SET lead = COALESCE(lead, lead_planner) WHERE lead IS NULL OR lead = ''")
    if "support_planner" in cols:
        cur.execute("UPDATE projects SET support = COALESCE(support, support_planner) WHERE support IS NULL OR support = ''")
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

def planners_df():
    c = conn()
    df = pd.read_sql_query("SELECT name, weekly_capacity, active FROM planners ORDER BY name", c)
    c.close()
    return df

def active_planners_df():
    df = planners_df()
    return df[df["active"] == 1][["name", "weekly_capacity"]].copy()

def projects_df():
    c = conn()
    df = pd.read_sql_query("SELECT * FROM projects ORDER BY created_at DESC, id DESC", c)
    c.close()

    # Normalize columns regardless of previous schema
    rename_map = {}
    if "lead_planner" in df.columns and "lead" not in df.columns:
        rename_map["lead_planner"] = "lead"
    if "support_planner" in df.columns and "support" not in df.columns:
        rename_map["support_planner"] = "support"
    if rename_map:
        df = df.rename(columns=rename_map)

    for col, default in {
        "status": "Active",
        "quest_type": "BAU",
        "priority": "Medium",
        "effort_xp": 8,
        "lead": None,
        "support": None,
        "client": "",
        "brief": "",
    }.items():
        if col not in df.columns:
            df[col] = default

    return df

def adjusted_xp(xp, priority, qtype):
    return round(float(xp) * PRIORITY_MULT.get(priority, 1.0) * QUEST_TYPES.get(qtype, 1.0), 1)

def add_project(data):
    c = conn()
    cur = c.cursor()
    cur.execute(
        """
        INSERT INTO projects(title, client, brief, status, quest_type, priority, effort_xp, start_date, due_date, lead, support, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        data
    )
    c.commit()
    c.close()

def delete_project(pid):
    c = conn()
    cur = c.cursor()
    cur.execute("DELETE FROM projects WHERE id=?", (int(pid),))
    c.commit()
    c.close()

def upsert_planner(name, capacity, active):
    c = conn()
    cur = c.cursor()
    cur.execute("SELECT id FROM planners WHERE name=?", (name,))
    row = cur.fetchone()
    if row:
        cur.execute("UPDATE planners SET weekly_capacity=?, active=? WHERE name=?", (int(capacity), int(active), name))
    else:
        cur.execute("INSERT INTO planners(name, weekly_capacity, active) VALUES (?, ?, ?)", (name, int(capacity), int(active)))
    c.commit()
    c.close()

def compute_load(planners, projects):
    out = planners.copy()
    loads = {n: 0.0 for n in out["name"].tolist()}
    active = projects[projects["status"] == "Active"].copy()

    for _, r in active.iterrows():
        xp = adjusted_xp(r.get("effort_xp", 8), r.get("priority", "Medium"), r.get("quest_type", "BAU"))
        lead = r.get("lead")
        support = r.get("support")

        if pd.notna(lead) and lead in loads:
            loads[lead] += xp * 0.7

        if pd.notna(support) and support in loads and support != lead:
            loads[support] += xp * 0.3

    out["XP Load"] = out["name"].map(lambda n: round(loads.get(n, 0.0), 1))
    out["Load %"] = out.apply(
        lambda r: round((r["XP Load"] / r["weekly_capacity"]) * 100, 1) if r["weekly_capacity"] else 0.0,
        axis=1
    )
    out = out.rename(columns={"name": "Planner", "weekly_capacity": "Capacity"})
    return out[["Planner", "Capacity", "XP Load", "Load %"]]

def suggest_assignment(planners, projects, xp, priority, qtype):
    current = compute_load(planners.copy(), projects)
    cap_map = {row["Planner"]: row["Capacity"] for _, row in current.iterrows()}
    load_map = {row["Planner"]: row["XP Load"] for _, row in current.iterrows()}
    names = current["Planner"].tolist()

    adjusted = adjusted_xp(xp, priority, qtype)
    best_pair = None
    best_score = None

    for lead in names:
        for support in ["None"] + names:
            temp = load_map.copy()
            temp[lead] += adjusted * 0.7
            if support != "None" and support != lead:
                temp[support] += adjusted * 0.3

            pcts = [(temp[name] / cap_map[name]) * 100 if cap_map[name] else 999 for name in names]
            score = (max(pcts), sum(pcts))

            if best_score is None or score < best_score:
                best_score = score
                best_pair = (lead, support)

    return best_pair, round(best_score[0], 1)

def week_start(d):
    return d - timedelta(days=d.weekday())

def weekly_grid(planners, projects, weeks=8):
    start = week_start(date.today())
    week_dates = [start + timedelta(days=7 * i) for i in range(weeks)]
    grid = pd.DataFrame(0.0, index=planners["name"].tolist(), columns=[d.isoformat() for d in week_dates])

    active = projects[projects["status"] == "Active"].copy()

    for _, r in active.iterrows():
        anchor = r.get("due_date") or r.get("start_date")
        try:
            d = datetime.fromisoformat(anchor).date() if anchor else date.today()
        except Exception:
            d = date.today()

        key = week_start(d).isoformat()
        if key not in grid.columns:
            continue

        xp = adjusted_xp(r.get("effort_xp", 8), r.get("priority", "Medium"), r.get("quest_type", "BAU"))
        lead = r.get("lead")
        support = r.get("support")

        if pd.notna(lead) and lead in grid.index:
            grid.loc[lead, key] += xp * 0.7
        if pd.notna(support) and support in grid.index and support != lead:
            grid.loc[support, key] += xp * 0.3

    return grid.round(1), week_dates

init_db()
seed()

st.markdown('<div class="block"><h2>🕹️ Traffic Quest</h2><p>Strategy workload board</p></div>', unsafe_allow_html=True)

page = st.sidebar.radio("Menu", ["Dashboard", "Add Task", "Tasks", "Dungeon Weeks", "Settings"])

pl = planners_df()
active_pl = active_planners_df()
pr = projects_df()

if page == "Dashboard":
    active_count = int((pr["status"] == "Active").sum()) if not pr.empty else 0
    hold_count = int((pr["status"] == "On Hold").sum()) if not pr.empty else 0
    done_count = int((pr["status"] == "Done").sum()) if not pr.empty else 0
    critical_count = int((pr["priority"] == "Critical").sum()) if not pr.empty else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(f'<div class="metric-card"><div class="metric-label green">ACTIVE</div><div class="metric-value green">{active_count}</div></div>', unsafe_allow_html=True)
    c2.markdown(f'<div class="metric-card"><div class="metric-label yellow">ON HOLD</div><div class="metric-value yellow">{hold_count}</div></div>', unsafe_allow_html=True)
    c3.markdown(f'<div class="metric-card"><div class="metric-label blue">DONE</div><div class="metric-value blue">{done_count}</div></div>', unsafe_allow_html=True)
    c4.markdown(f'<div class="metric-card"><div class="metric-label red">CRITICAL</div><div class="metric-value red">{critical_count}</div></div>', unsafe_allow_html=True)

    st.subheader("Team Load")
    st.dataframe(compute_load(active_pl.copy(), pr), use_container_width=True, hide_index=True)

    st.subheader("Current Tasks")
    if pr.empty:
        st.info("No tasks yet.")
    else:
        board = pr.copy()
        board["Adj XP"] = board.apply(lambda r: adjusted_xp(r["effort_xp"], r["priority"], r["quest_type"]), axis=1)
        board = board.rename(columns={
            "title": "Project",
            "client": "Client",
            "status": "Status",
            "quest_type": "Type",
            "priority": "Priority",
            "effort_xp": "XP",
            "lead": "Lead",
            "support": "Support",
        })
        show_cols = [c for c in ["id", "Project", "Client", "Status", "Type", "Priority", "XP", "Adj XP", "Lead", "Support"] if c in board.columns]
        if "id" in show_cols:
            board = board.rename(columns={"id": "ID"})
            show_cols = ["ID" if c == "id" else c for c in show_cols]
        st.dataframe(board[show_cols], use_container_width=True, hide_index=True)

elif page == "Add Task":
    st.subheader("Add Task")

    title = st.text_input("Project")
    client = st.text_input("Client")
    brief = st.text_area("Brief")

    col1, col2, col3 = st.columns(3)
    with col1:
        qtype = st.selectbox("Type", list(QUEST_TYPES.keys()))
    with col2:
        priority = st.selectbox("Priority", list(PRIORITY_MULT.keys()), index=1)
    with col3:
        xp = st.number_input("XP", 1, 100, 8)

    st.caption(f"Adjusted XP: {adjusted_xp(xp, priority, qtype)}")

    if not active_pl.empty and st.button("Auto-Suggest"):
        pair, max_pct = suggest_assignment(active_pl.copy(), pr, xp, priority, qtype)
        st.session_state["lead_pick"] = pair[0]
        st.session_state["support_pick"] = pair[1]
        st.success(f"Suggested lead: {pair[0]} | support: {pair[1]} | projected max load: {max_pct}%")

    planner_names = active_pl["name"].tolist() if not active_pl.empty else []
    lead_default = st.session_state.get("lead_pick", planner_names[0] if planner_names else None)
    support_default = st.session_state.get("support_pick", "None")

    col4, col5 = st.columns(2)
    with col4:
        lead = st.selectbox("Lead", planner_names, index=planner_names.index(lead_default) if lead_default in planner_names else 0)
    with col5:
        support_choices = ["None"] + planner_names
        support = st.selectbox("Support", support_choices, index=support_choices.index(support_default) if support_default in support_choices else 0)

    col6, col7 = st.columns(2)
    with col6:
        start_date = st.date_input("Start", value=date.today())
    with col7:
        due_date = st.date_input("Due", value=None)

    if st.button("Save Task"):
        if not title.strip():
            st.error("Project is required.")
        else:
            add_project((
                title.strip(),
                client.strip(),
                brief.strip(),
                "Active",
                qtype,
                priority,
                int(xp),
                start_date.isoformat() if start_date else None,
                due_date.isoformat() if due_date else None,
                lead,
                None if support == "None" else support,
                datetime.now().isoformat()
            ))
            st.success("Task saved.")
            st.rerun()

elif page == "Tasks":
    st.subheader("Tasks")

    if pr.empty:
        st.info("No tasks yet.")
    else:
        view = pr.copy().rename(columns={
            "id": "ID",
            "title": "Project",
            "client": "Client",
            "status": "Status",
            "quest_type": "Type",
            "priority": "Priority",
            "lead": "Lead",
            "support": "Support",
        })
        show_cols = [c for c in ["ID", "Project", "Client", "Status", "Type", "Priority", "Lead", "Support"] if c in view.columns]
        st.dataframe(view[show_cols], use_container_width=True, hide_index=True)

        st.subheader("Delete Task")
        pid = st.selectbox("Task ID", view["ID"].tolist())
        confirm = st.checkbox("I’m sure I want to delete this task")
        if st.button("Delete Task"):
            if not confirm:
                st.warning("Please confirm deletion first.")
            else:
                delete_project(pid)
                st.success("Task deleted.")
                st.rerun()

elif page == "Dungeon Weeks":
    st.subheader("Dungeon Weeks")

    weeks = st.number_input("Weeks", 4, 16, 8)
    grid, week_cols = weekly_grid(active_pl.copy(), pr, int(weeks))
    cap_map = {row["name"]: row["weekly_capacity"] for _, row in active_pl.iterrows()}

    if grid.empty:
        st.info("No active planners or tasks.")
    else:
        display = pd.DataFrame(index=grid.index)
        for d in week_cols:
            key = d.isoformat()
            label = d.strftime("Wk of %b %d")
            display[label] = [
                f"{grid.loc[name, key]:.1f}xp ({((grid.loc[name, key] / cap_map[name]) * 100) if cap_map[name] else 0:.1f}%)"
                for name in grid.index
            ]
        st.dataframe(display, use_container_width=True)

elif page == "Settings":
    st.subheader("Planners")
    planner_view = pl.rename(columns={"name": "Planner", "weekly_capacity": "Capacity", "active": "Active"})
    st.dataframe(planner_view[["Planner", "Capacity", "Active"]], use_container_width=True, hide_index=True)

    st.subheader("Add / Update Planner")
    name = st.text_input("Planner")
    capacity = st.number_input("Capacity", 5, 100, 40)
    active = st.checkbox("Active", value=True)

    if st.button("Save Planner"):
        if not name.strip():
            st.error("Planner name is required.")
        else:
            upsert_planner(name.strip(), int(capacity), 1 if active else 0)
            st.success("Planner saved.")
            st.rerun()
