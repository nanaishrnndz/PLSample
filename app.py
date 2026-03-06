
import sqlite3
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Traffic Quest: Strategy Guild Board",
    page_icon="🕹️",
    layout="wide",
)

DB_PATH = "data/traffic.db"

RETRO_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Press+Start+2P&display=swap');
:root{
  --bg:#0b1020; --panel:#111a33; --panel2:#0f1730; --text:#e6f0ff; --muted:#9bb3d1;
  --accent:#7CFF6B; --warn:#FFD36B; --danger:#FF6B6B; --border:#2a3a66;
}
html, body, [class*="css"]  {
  font-family: 'Press Start 2P', ui-monospace, monospace !important;
  background: radial-gradient(circle at 20% 20%, #101a3a 0%, var(--bg) 55%, #070a14 100%) !important;
  color: var(--text) !important;
}
.stApp { background: transparent !important; }
h1, h2, h3, h4 { letter-spacing: 0.5px; }
.retro-card {
  border: 2px solid var(--border);
  background: linear-gradient(180deg, var(--panel) 0%, var(--panel2) 100%);
  padding: 14px; border-radius: 10px; box-shadow: 0 8px 0 rgba(0,0,0,0.35);
}
.retro-badge {
  display:inline-block; padding: 6px 8px; border: 2px solid var(--border); border-radius: 10px;
  background: #0c1330; color: var(--text); margin-right: 6px; margin-bottom: 6px;
}
.quest-title{ font-size: 14px; line-height: 1.4; }
.small { font-size: 11px; color: var(--muted); }
hr{ border: none; border-top: 2px dashed var(--border); margin: 10px 0; }
.stButton>button {
  border: 2px solid var(--border) !important;
  background: #0c1330 !important;
  color: var(--text) !important;
  border-radius: 10px !important;
  padding: 10px 14px !important;
  box-shadow: 0 5px 0 rgba(0,0,0,0.35) !important;
}
.stButton>button:active {
  transform: translateY(3px);
  box-shadow: 0 2px 0 rgba(0,0,0,0.35) !important;
}
.stTextInput input, .stTextArea textarea, .stSelectbox div, .stDateInput input, .stNumberInput input {
  border: 2px solid var(--border) !important;
  background: #0c1330 !important;
  color: var(--text) !important;
  border-radius: 10px !important;
}
[data-testid="stMetricValue"]{ font-size: 18px !important; }
.pixel-divider {
  height: 8px;
  background: linear-gradient(
      90deg,
      transparent 0 6px,
      rgba(124,255,107,0.25) 6px 8px,
      transparent 8px 14px,
      rgba(255,211,107,0.25) 14px 16px,
      transparent 16px 22px,
      rgba(255,107,107,0.25) 22px 24px,
      transparent 24px 100%
  );
  border: 2px solid var(--border); border-radius: 10px;
}
.warn { color: var(--warn); } .danger { color: var(--danger); } .accent { color: var(--accent); }
</style>
"""

st.markdown(RETRO_CSS, unsafe_allow_html=True)

QUEST_TYPES = {
    "BAU / Always-On": 1.0,
    "Campaign / Launch": 1.15,
    "Pitch": 1.35,
    "Awards Case / Effies": 1.25,
    "Research / Foresight": 1.05,
    "Crisis / Rush": 1.5,
}
PRIORITY_MULT = {"Low": 0.75, "Medium": 1.0, "High": 1.25, "Critical": 1.5}
DEFAULT_WEEK_WINDOW = 8
WEEK_START = 0


def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def ensure_column(conn, table, column, col_def_sql):
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    cols = [r[1] for r in cur.fetchall()]
    if column not in cols:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def_sql}")


def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS planners (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            weekly_capacity INTEGER NOT NULL DEFAULT 40,
            active INTEGER NOT NULL DEFAULT 1
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS projects (
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
    ensure_column(conn, "projects", "quest_type", "TEXT NOT NULL DEFAULT 'BAU / Always-On'")
    conn.commit()
    conn.close()


def seed_if_empty():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM planners")
    if cur.fetchone()[0] == 0:
        cur.executemany(
            "INSERT INTO planners (name, weekly_capacity, active) VALUES (?, ?, 1)",
            [("Merc", 40), ("Phyllis", 40), ("Fritz", 40), ("Nanais", 45)]
        )
        conn.commit()
    conn.close()


def fetch_planners(active_only=True):
    conn = get_conn()
    q = "SELECT name, weekly_capacity, active FROM planners"
    if active_only:
        q += " WHERE active=1"
    df = pd.read_sql_query(q + " ORDER BY name", conn)
    conn.close()
    return df


def fetch_projects():
    conn = get_conn()
    df = pd.read_sql_query(
        "SELECT * FROM projects ORDER BY due_date IS NULL, due_date ASC, created_at DESC",
        conn
    )
    conn.close()
    return df


def insert_project(p):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO projects
        (title, client, brief, status, quest_type, priority, effort_xp, start_date, due_date, lead_planner, support_planner, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        p["title"], p["client"], p["brief"], p["status"], p["quest_type"], p["priority"], p["effort_xp"],
        p["start_date"], p["due_date"], p["lead_planner"], p["support_planner"], p["created_at"]
    ))
    conn.commit()
    conn.close()


def update_project_status(project_id, new_status):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE projects SET status=? WHERE id=?", (new_status, project_id))
    conn.commit()
    conn.close()


def update_project_fields(project_id, lead, support, effort_xp, priority, due_date, quest_type):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        UPDATE projects
        SET lead_planner=?, support_planner=?, effort_xp=?, priority=?, due_date=?, quest_type=?
        WHERE id=?
    """, (lead, support, effort_xp, priority, due_date, quest_type, project_id))
    conn.commit()
    conn.close()


def upsert_planner(name, capacity, active):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id FROM planners WHERE name=?", (name,))
    row = cur.fetchone()
    if row:
        cur.execute("UPDATE planners SET weekly_capacity=?, active=? WHERE name=?", (capacity, active, name))
    else:
        cur.execute("INSERT INTO planners (name, weekly_capacity, active) VALUES (?, ?, ?)", (name, capacity, active))
    conn.commit()
    conn.close()


def adjusted_xp(effort_xp, priority, quest_type):
    return round(float(effort_xp) * PRIORITY_MULT.get(priority, 1.0) * QUEST_TYPES.get(quest_type, 1.0), 1)


def compute_load(planners_df, projects_df):
    active = projects_df[projects_df["status"] == "Active"].copy()
    planners_df = planners_df.copy()

    if active.empty:
        planners_df["load_xp"] = 0.0
        planners_df["load_pct"] = 0.0
        planners_df["state"] = "OK"
        return planners_df, active

    active["adj_xp"] = active.apply(
        lambda r: adjusted_xp(int(r["effort_xp"]), str(r["priority"]), str(r.get("quest_type") or "BAU / Always-On")),
        axis=1
    )

    load_map = {n: 0.0 for n in planners_df["name"].tolist()}
    for _, r in active.iterrows():
        lead = r.get("lead_planner")
        sup = r.get("support_planner")
        xp = float(r["adj_xp"])
        if lead in load_map:
            load_map[lead] += xp * 0.70
        if sup in load_map and sup and sup != lead:
            load_map[sup] += xp * 0.30

    planners_df["load_xp"] = planners_df["name"].map(lambda n: round(load_map.get(n, 0.0), 1))
    planners_df["load_pct"] = planners_df.apply(
        lambda r: 0.0 if r["weekly_capacity"] <= 0 else round((r["load_xp"] / r["weekly_capacity"]) * 100, 1),
        axis=1
    )

    def state(p):
        if p >= 110:
            return "OVERLOADED"
        if p >= 90:
            return "FULL"
        if p >= 70:
            return "BUSY"
        return "OK"

    planners_df["state"] = planners_df["load_pct"].map(state)
    return planners_df, active


def retro_state_line(state):
    if state == "OVERLOADED":
        return "💀 <span class='danger'>OVERLOADED</span>"
    if state == "FULL":
        return "🧨 <span class='warn'>FULL</span>"
    if state == "BUSY":
        return "⚔️ <span class='warn'>BUSY</span>"
    return "🛡️ <span class='accent'>OK</span>"


def week_start(d):
    return d - timedelta(days=(d.weekday() - WEEK_START) % 7)


def parse_iso_to_date(s):
    if not s or pd.isna(s):
        return None
    try:
        return datetime.fromisoformat(str(s)).date()
    except Exception:
        return None


def compute_weekly_load(planners_df, projects_df, start_week, weeks):
    week_starts = [start_week + timedelta(days=7 * i) for i in range(weeks)]
    cols = [ws.isoformat() for ws in week_starts]
    grid = pd.DataFrame(0.0, index=planners_df["name"].tolist(), columns=cols)

    active = projects_df[projects_df["status"] == "Active"].copy()
    if active.empty:
        return grid, week_starts

    today = date.today()
    for _, r in active.iterrows():
        due = parse_iso_to_date(r.get("due_date"))
        stt = parse_iso_to_date(r.get("start_date"))
        anchor = due or stt or today
        ws = week_start(anchor)
        if ws < start_week or ws > (start_week + timedelta(days=7 * (weeks - 1))):
            continue

        col = ws.isoformat()
        xp = adjusted_xp(int(r["effort_xp"]), str(r["priority"]), str(r.get("quest_type") or "BAU / Always-On"))
        lead = r.get("lead_planner")
        sup = r.get("support_planner")
        if lead in grid.index:
            grid.loc[lead, col] += xp * 0.70
        if sup in grid.index and sup and sup != lead:
            grid.loc[sup, col] += xp * 0.30

    return grid.round(1), week_starts


def suggest_assignment(planners_df, projects_df, base_xp, priority, quest_type):
    load_df, _ = compute_load(planners_df[["name", "weekly_capacity"]], projects_df)
    base_load = {r["name"]: float(r["load_xp"]) for _, r in load_df.iterrows()}
    caps = {r["name"]: float(r["weekly_capacity"]) for _, r in planners_df.iterrows()}
    names = planners_df["name"].tolist()
    xp = adjusted_xp(int(base_xp), str(priority), str(quest_type))

    best_pair = None
    best_score = None
    best_detail = None

    for lead in names:
        for sup in ["—"] + names:
            proj = dict(base_load)
            proj[lead] += xp * 0.70
            if sup != "—" and sup != lead:
                proj[sup] += xp * 0.30

            pcts = []
            for n in names:
                cap = caps.get(n, 40.0)
                pcts.append((proj[n] / cap) * 100.0 if cap > 0 else 999.0)

            score = (max(pcts), sum(pcts))
            if best_score is None or score < best_score:
                best_score = score
                best_pair = (lead, None if sup == "—" else sup)
                best_detail = {"projected_max_pct": round(score[0], 1)}

    return best_pair, best_detail


init_db()
seed_if_empty()

st.markdown(
    """
    <div class="retro-card">
      <div class="quest-title">🕹️ TRAFFIC QUEST: Strategy Guild Board</div>
      <div class="small">Manage briefs like quests. Assign heroes. Avoid party wipes (overload).</div>
    </div>
    """,
    unsafe_allow_html=True,
)
st.markdown("<div class='pixel-divider'></div>", unsafe_allow_html=True)

page = st.sidebar.radio(
    "NAV MENU",
    ["🏰 Guild Dashboard", "📜 Add Quest (New Project)", "🧭 Quest Log (Projects)", "🗓️ Dungeon Weeks", "🧰 Guild Settings"],
    index=0,
)

planners = fetch_planners(active_only=False)
projects = fetch_projects()

if page == "🏰 Guild Dashboard":
    active_projects = projects[projects["status"] == "Active"]
    hold_projects = projects[projects["status"] == "On Hold"]
    done_projects = projects[projects["status"] == "Done"]

    planners_active = planners[planners["active"] == 1].copy()
    load_df, _ = compute_load(planners_active[["name", "weekly_capacity"]], projects)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Active Quests", int(len(active_projects)))
    c2.metric("On Hold", int(len(hold_projects)))
    c3.metric("Completed", int(len(done_projects)))
    c4.metric("Party Risk", int((load_df["state"].isin(["FULL", "OVERLOADED"])).sum()))

    st.markdown("<hr>", unsafe_allow_html=True)
    left, right = st.columns([1.2, 1])

    with left:
        st.subheader("👥 Party Load (Strategy Team)")
        overloaded = load_df[load_df["state"] == "OVERLOADED"]
        full = load_df[load_df["state"] == "FULL"]

        if not overloaded.empty:
            st.error(f"💀 OVERLOADED: {', '.join(overloaded['name'].tolist())} — reinforcements needed!")
        elif not full.empty:
            st.warning(f"🧨 FULL: {', '.join(full['name'].tolist())} — add support or delay quests.")
        else:
            st.success("🛡️ Party is stable. You may accept new quests.")

        for _, r in load_df.sort_values("load_pct", ascending=False).iterrows():
            st.markdown(
                f"""
                <div class="retro-card" style="margin-bottom:10px;">
                  <div class="quest-title">🧙 {r['name']} — {retro_state_line(r['state'])}</div>
                  <div class="small">XP Load: {r['load_xp']} / {r['weekly_capacity']} ({r['load_pct']}%)</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.progress(min(max(r["load_pct"] / 100.0, 0.0), 1.0))

    with right:
        st.subheader("🗺️ Active Quests (Soonest Due)")
        if active_projects.empty:
            st.info("No active quests yet. Add your first project in 📜 Add Quest.")
        else:
            def fmt(d):
                if not d or pd.isna(d):
                    return ""
                try:
                    return datetime.fromisoformat(d).strftime("%b %d, %Y")
                except Exception:
                    return str(d)

            for _, r in active_projects.head(12).iterrows():
                due = fmt(r.get("due_date"))
                prio = r.get("priority", "Medium")
                qtype = r.get("quest_type", "BAU / Always-On")
                xp = int(r.get("effort_xp", 8))
                adj = adjusted_xp(xp, str(prio), str(qtype))

                st.markdown(
                    f"""
                    <div class="retro-card" style="margin-bottom:10px;">
                      <div class="quest-title">📌 {r['title']}</div>
                      <div class="small">
                        <span class="retro-badge">Client: {r.get('client','') or '—'}</span>
                        <span class="retro-badge">Type: {qtype}</span>
                        <span class="retro-badge">Priority: {prio}</span>
                        <span class="retro-badge">XP: {xp} → {adj}</span>
                      </div>
                      <div class="small">Lead: {r.get('lead_planner') or '—'} | Support: {r.get('support_planner') or '—'} | Due: {due or '—'}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

elif page == "📜 Add Quest (New Project)":
    st.subheader("📜 New Quest Intake")

    planners_active = planners[planners["active"] == 1]["name"].tolist()
    if not planners_active:
        st.error("No active planners found. Add planners in 🧰 Guild Settings.")
        st.stop()

    title = st.text_input("Quest Title (Project name)", placeholder="e.g., Brand relaunch strategy sprint")
    client = st.text_input("Client / Brand", placeholder="e.g., Client Name")
    brief = st.text_area("Brief / Notes", placeholder="Paste the brief / key asks / links / deliverables...", height=160)

    colA, colB, colC = st.columns(3)
    with colA:
        quest_type = st.selectbox("Quest Type", list(QUEST_TYPES.keys()), index=0)
    with colB:
        priority = st.selectbox("Urgency (Priority)", ["Low", "Medium", "High", "Critical"], index=1)
    with colC:
        effort_xp = st.number_input("Effort (Base XP)", min_value=1, max_value=100, value=8, step=1)

    st.caption(f"Adjusted XP = {adjusted_xp(int(effort_xp), priority, quest_type)}")

    col1, col2, col3 = st.columns(3)
    with col1:
        status = st.selectbox("Status", ["Active", "On Hold", "Done"], index=0)
    with col2:
        start = st.date_input("Start Date", value=date.today())
    with col3:
        due = st.date_input("Due Date", value=None)

    st.markdown("<hr>", unsafe_allow_html=True)
    st.subheader("🧠 Auto-suggest Party")

    if st.button("✨ Auto-suggest assignments"):
        planners_active_df = planners[planners["active"] == 1][["name", "weekly_capacity"]].copy()
        pair, detail = suggest_assignment(planners_active_df, projects, effort_xp, priority, quest_type)
        if pair:
            st.session_state["suggested_lead"] = pair[0]
            st.session_state["suggested_support"] = "—" if pair[1] is None else pair[1]
            st.success(
                f"Suggested Lead {st.session_state['suggested_lead']}, "
                f"Support {st.session_state['suggested_support']} "
                f"(projected max load ~{detail['projected_max_pct']}%)."
            )

    suggested_lead = st.session_state.get("suggested_lead", planners_active[0])
    suggested_support = st.session_state.get("suggested_support", "—")

    colL, colS = st.columns(2)
    with colL:
        lead = st.selectbox(
            "Lead Planner (Party Leader)",
            planners_active,
            index=planners_active.index(suggested_lead) if suggested_lead in planners_active else 0,
        )
    with colS:
        support_choices = ["—"] + planners_active
        support = st.selectbox(
            "Supporting Planner (Party Member)",
            support_choices,
            index=support_choices.index(suggested_support) if suggested_support in support_choices else 0,
        )

    if st.button("✅ Accept Quest (Save)"):
        if not title.strip():
            st.error("Quest Title is required.")
            st.stop()

        payload = {
            "title": title.strip(),
            "client": client.strip(),
            "brief": brief.strip(),
            "status": status,
            "quest_type": quest_type,
            "priority": priority,
            "effort_xp": int(effort_xp),
            "start_date": start.isoformat() if start else None,
            "due_date": due.isoformat() if due else None,
            "lead_planner": lead,
            "support_planner": None if support == "—" else support,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        insert_project(payload)
        st.success("🎉 Quest accepted!")

        planners_active_df = fetch_planners(active_only=True)[["name", "weekly_capacity"]]
        projects_now = fetch_projects()
        load_now, _ = compute_load(planners_active_df, projects_now)
        risky = load_now[load_now["state"].isin(["FULL", "OVERLOADED"])]
        if not risky.empty:
            st.warning(
                "⚠️ Party Load Warning: " +
                ", ".join([f"{r.name}({r.state}, {r.load_pct}%)" for r in risky.itertuples()])
            )

elif page == "🧭 Quest Log (Projects)":
    st.subheader("🧭 Quest Log")

    cols = st.columns([1, 1, 1, 1, 1])
    with cols[0]:
        status_filter = st.selectbox("Status", ["All", "Active", "On Hold", "Done"], index=0)
    with cols[1]:
        prio_filter = st.selectbox("Priority", ["All", "Low", "Medium", "High", "Critical"], index=0)
    with cols[2]:
        qtype_filter = st.selectbox("Quest Type", ["All"] + list(QUEST_TYPES.keys()), index=0)
    with cols[3]:
        lead_filter = st.selectbox("Lead", ["All"] + sorted(planners["name"].tolist()), index=0)
    with cols[4]:
        search = st.text_input("Search", placeholder="title / client / brief")

    df = projects.copy()
    if status_filter != "All":
        df = df[df["status"] == status_filter]
    if prio_filter != "All":
        df = df[df["priority"] == prio_filter]
    if qtype_filter != "All":
        df = df[df["quest_type"] == qtype_filter]
    if lead_filter != "All":
        df = df[df["lead_planner"] == lead_filter]
    if search.strip():
        s = search.strip().lower()
        df = df[
            df["title"].fillna("").str.lower().str.contains(s) |
            df["client"].fillna("").str.lower().str.contains(s) |
            df["brief"].fillna("").str.lower().str.contains(s)
        ]

    if df.empty:
        st.info("No quests match your filters.")
        st.stop()

    show = df[["id", "title", "client", "status", "quest_type", "priority", "effort_xp", "lead_planner", "support_planner", "due_date"]].copy()

    def fmt(d):
        if not d or pd.isna(d):
            return ""
        try:
            return datetime.fromisoformat(d).strftime("%b %d, %Y")
        except Exception:
            return str(d)

    show["due_date"] = show["due_date"].apply(fmt)
    st.dataframe(show, use_container_width=True, hide_index=True)

    st.markdown("<hr>", unsafe_allow_html=True)
    st.subheader("🛠️ Update a Quest")

    pick = st.selectbox("Pick Quest ID", df["id"].tolist())
    row = df[df["id"] == pick].iloc[0]
    planners_active = planners[planners["active"] == 1]["name"].tolist()

    col1, col2, col3 = st.columns(3)
    with col1:
        new_status = st.selectbox("New Status", ["Active", "On Hold", "Done"], index=["Active", "On Hold", "Done"].index(row["status"]))
    with col2:
        new_priority = st.selectbox("New Priority", ["Low", "Medium", "High", "Critical"], index=["Low", "Medium", "High", "Critical"].index(row["priority"]))
    with col3:
        q_keys = list(QUEST_TYPES.keys())
        current_q = row.get("quest_type", "BAU / Always-On")
        new_qtype = st.selectbox("New Quest Type", q_keys, index=q_keys.index(current_q) if current_q in q_keys else 0)

    colA, colB, colC = st.columns(3)
    with colA:
        new_xp = st.number_input("Base Effort XP", min_value=1, max_value=100, value=int(row["effort_xp"]), step=1)
    with colB:
        new_lead = st.selectbox("Lead Planner", planners_active, index=planners_active.index(row["lead_planner"]) if row["lead_planner"] in planners_active else 0)
    with colC:
        support_choices = ["—"] + planners_active
        current_support = row["support_planner"] if pd.notna(row["support_planner"]) else "—"
        new_support = st.selectbox("Supporting Planner", support_choices, index=support_choices.index(current_support) if current_support in support_choices else 0)

    current_due = parse_iso_to_date(row["due_date"]) if pd.notna(row["due_date"]) and row["due_date"] else None
    new_due = st.date_input("Due Date", value=current_due)

    st.caption(f"Adjusted XP now = {adjusted_xp(int(new_xp), new_priority, new_qtype)}")

    if st.button("💾 Save Updates"):
        update_project_fields(
            int(pick),
            new_lead,
            None if new_support == "—" else new_support,
            int(new_xp),
            new_priority,
            new_due.isoformat() if new_due else None,
            new_qtype,
        )
        update_project_status(int(pick), new_status)
        st.success("Saved.")
        st.rerun()

elif page == "🗓️ Dungeon Weeks":
    st.subheader("🗓️ Dungeon Weeks (Weekly Load Projection)")

    planners_active = planners[planners["active"] == 1][["name", "weekly_capacity"]].copy()
    if planners_active.empty:
        st.error("No active planners found.")
        st.stop()

    weeks = st.number_input("Weeks to show", min_value=4, max_value=16, value=DEFAULT_WEEK_WINDOW, step=1)
    st.caption("Heuristic: each active quest is counted in its due week (or start week if no due date).")

    start_week = week_start(date.today())
    grid, week_starts = compute_weekly_load(planners_active, projects, start_week, int(weeks))
    caps = planners_active.set_index("name")["weekly_capacity"].to_dict()

    display = pd.DataFrame(index=grid.index)
    for ws in week_starts:
        col = ws.isoformat()
        label = ws.strftime("Wk of %b %d")
        display[label] = [
            f"{grid.loc[name, col]:.1f}xp ({(float(grid.loc[name, col]) / float(caps.get(name, 40)) * 100.0):.1f}%)"
            for name in grid.index
        ]

    st.dataframe(display, use_container_width=True)

    st.markdown("<hr>", unsafe_allow_html=True)
    st.subheader("🚨 Weekly Party Risk")

    alerts = []
    for ws in week_starts:
        col = ws.isoformat()
        for name in grid.index:
            cap = float(caps.get(name, 40))
            pct = (float(grid.loc[name, col]) / cap * 100.0) if cap > 0 else 999.0
            if pct >= 110:
                alerts.append((ws.strftime("%b %d, %Y"), name, round(pct, 1), "OVERLOADED"))
            elif pct >= 90:
                alerts.append((ws.strftime("%b %d, %Y"), name, round(pct, 1), "FULL"))

    if not alerts:
        st.success("No FULL/OVERLOADED weeks detected in this window. 🛡️")
    else:
        st.dataframe(pd.DataFrame(alerts, columns=["Week Start", "Planner", "Projected %", "State"]), use_container_width=True, hide_index=True)

elif page == "🧰 Guild Settings":
    st.subheader("🧰 Guild Settings")

    roster = fetch_planners(active_only=False)
    st.dataframe(roster, use_container_width=True, hide_index=True)

    st.markdown("<hr>", unsafe_allow_html=True)
    st.subheader("➕ Add / Update Planner")

    name = st.text_input("Planner Name", placeholder="e.g., Aly")
    capacity = st.number_input("Weekly Capacity (XP)", min_value=5, max_value=100, value=40, step=1)
    active = st.checkbox("Active", value=True)

    if st.button("Save Planner"):
        if not name.strip():
            st.error("Planner name is required.")
            st.stop()
        upsert_planner(name.strip(), int(capacity), 1 if active else 0)
        st.success("Planner saved.")
        st.rerun()

    st.markdown("<hr>", unsafe_allow_html=True)
    st.subheader("🧠 Rules")
    st.write(
        "- Adjusted XP = Base XP × Priority × Quest Type\n"
        "- Load split: Lead 70%, Support 30%\n"
        "- Alerts: BUSY ≥ 70%, FULL ≥ 90%, OVERLOADED ≥ 110%\n"
        "- Dungeon Weeks counts each active quest in its due/start week"
    )

st.sidebar.markdown("---")
st.sidebar.caption("🕹️ Built for traffic officers managing strategy workload.")
