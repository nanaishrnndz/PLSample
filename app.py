
import os
import sqlite3
from datetime import date, datetime
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Traffic Quest", page_icon="🕹️", layout="wide")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "traffic.db")
os.makedirs(DATA_DIR, exist_ok=True)

QUEST_TYPES = {"BAU":1.0,"Campaign":1.15,"Pitch":1.35,"Awards":1.25,"Research":1.05,"Rush":1.5}
PRIORITY_MULT = {"Low":0.75,"Medium":1.0,"High":1.25,"Critical":1.5}

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Press+Start+2P&display=swap');
html, body, [class*="css"] {font-family:'Press Start 2P',monospace!important;}
.stApp {background: radial-gradient(circle at 20% 20%, #101a3a 0%, #0b1020 55%, #070a14 100%)!important;color:white;}
.block {border:2px solid #2a3a66;background:linear-gradient(180deg,#111a33 0%,#0f1730 100%);padding:12px;border-radius:10px;margin-bottom:10px;}
.green{color:#4cff4c;} .yellow{color:#ffd84c;} .blue{color:#66ccff;} .red{color:#ff4c4c;}
</style>
""", unsafe_allow_html=True)

def conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    c=conn();cur=c.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS planners(id INTEGER PRIMARY KEY,name TEXT UNIQUE,weekly_capacity INTEGER DEFAULT 40,active INTEGER DEFAULT 1)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS projects(id INTEGER PRIMARY KEY,title TEXT,client TEXT,brief TEXT,status TEXT,quest_type TEXT,priority TEXT,effort_xp INTEGER,start_date TEXT,due_date TEXT,lead TEXT,support TEXT,created_at TEXT)""")
    c.commit();c.close()

def seed():
    c=conn();cur=c.cursor()
    cur.execute("SELECT COUNT(*) FROM planners")
    if cur.fetchone()[0]==0:
        cur.executemany("INSERT INTO planners(name,weekly_capacity,active) VALUES (?, ?, 1)",[("Merc",40),("Phyllis",40),("Fritz",40),("Nanais",45)])
        c.commit()
    c.close()

def planners_df():
    c=conn()
    df=pd.read_sql_query("SELECT name,weekly_capacity FROM planners WHERE active=1",c)
    c.close();return df

def projects_df():
    c=conn()
    df=pd.read_sql_query("SELECT * FROM projects ORDER BY created_at DESC",c)
    c.close();return df

def adjusted_xp(xp,p,q): return round(xp*PRIORITY_MULT.get(p,1)*QUEST_TYPES.get(q,1),1)

def add_project(data):
    c=conn();cur=c.cursor()
    cur.execute("""INSERT INTO projects(title,client,brief,status,quest_type,priority,effort_xp,start_date,due_date,lead,support,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",data)
    c.commit();c.close()

def delete_project(pid):
    c=conn();cur=c.cursor()
    cur.execute("DELETE FROM projects WHERE id=?", (pid,))
    c.commit();c.close()

def compute_load(planners,projects):
    loads={n:0 for n in planners["name"]}
    active=projects[projects["status"]=="Active"]
    for _,r in active.iterrows():
        xp=adjusted_xp(r["effort_xp"],r["priority"],r["quest_type"])
        if r["lead"] in loads: loads[r["lead"]]+=xp*0.7
        if r["support"] in loads and r["support"]!=r["lead"]: loads[r["support"]]+=xp*0.3
    planners["XP Load"]=planners["name"].map(loads)
    planners["Load %"]=(planners["XP Load"]/planners["weekly_capacity"]*100).round(1)
    planners.rename(columns={"name":"Planner","weekly_capacity":"Capacity"},inplace=True)
    return planners

init_db();seed()

st.markdown('<div class="block"><h3>🕹 Traffic Quest</h3><p>Strategy workload board</p></div>',unsafe_allow_html=True)

page=st.sidebar.radio("Menu",["Dashboard","Add Task","Tasks","Settings"])

pl=planners_df()
pr=projects_df()

if page=="Dashboard":
    active=pr[pr.status=="Active"].shape[0]
    hold=pr[pr.status=="On Hold"].shape[0]
    done=pr[pr.status=="Done"].shape[0]
    critical=pr[pr.priority=="Critical"].shape[0]

    c1,c2,c3,c4=st.columns(4)
    c1.markdown(f"<h3 class='green'>Active: {active}</h3>",unsafe_allow_html=True)
    c2.markdown(f"<h3 class='yellow'>On Hold: {hold}</h3>",unsafe_allow_html=True)
    c3.markdown(f"<h3 class='blue'>Done: {done}</h3>",unsafe_allow_html=True)
    c4.markdown(f"<h3 class='red'>Critical: {critical}</h3>",unsafe_allow_html=True)

    st.subheader("Team Load")
    st.dataframe(compute_load(pl.copy(),pr),use_container_width=True)

elif page=="Add Task":
    title=st.text_input("Project")
    client=st.text_input("Client")
    brief=st.text_area("Brief")

    col1,col2,col3=st.columns(3)
    with col1: qtype=st.selectbox("Type",list(QUEST_TYPES.keys()))
    with col2: priority=st.selectbox("Priority",list(PRIORITY_MULT.keys()))
    with col3: xp=st.number_input("XP",1,100,8)

    st.caption(f"Adjusted XP: {adjusted_xp(xp,priority,qtype)}")

    col4,col5=st.columns(2)
    with col4: lead=st.selectbox("Lead",pl["name"].tolist())
    with col5: support=st.selectbox("Support",["None"]+pl["name"].tolist())

    if st.button("Save Task"):
        add_project((title,client,brief,"Active",qtype,priority,xp,date.today().isoformat(),None,lead,None if support=="None" else support,datetime.now().isoformat()))
        st.success("Task saved")
        st.rerun()

elif page=="Tasks":
    st.subheader("Tasks")

    if pr.empty:
        st.info("No tasks yet")
    else:
        view=pr.rename(columns={"id":"ID","title":"Project","client":"Client","status":"Status","priority":"Priority","lead":"Lead","support":"Support"})
        st.dataframe(view[["ID","Project","Client","Status","Priority","Lead","Support"]],use_container_width=True)

        st.subheader("Delete Task")
        pid=st.selectbox("Task ID",view["ID"].tolist())
        if st.button("Delete Task"):
            delete_project(pid)
            st.success("Task deleted")
            st.rerun()

elif page=="Settings":
    st.subheader("Planners")
    st.dataframe(pl.rename(columns={"name":"Planner","weekly_capacity":"Capacity"}),use_container_width=True)
