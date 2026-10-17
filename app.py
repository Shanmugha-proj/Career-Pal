"""Career-Pal: what should I learn next? A graph knows.

Run: python -m streamlit run app.py
"""
import json
import sys

import pandas as pd
import streamlit as st

import graph
import llm
from skills import LEARN_DAYS, LEVEL_LABELS

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

CID = "demo"
TOTAL_JOBS = 300

st.set_page_config(page_title="Career-Pal", page_icon="🧭", layout="wide")
st.markdown("""
<style>
  .big   { font-size: 64px; font-weight: 800; line-height: 1.05; margin: 0; }
  .big em { font-style: normal; color: #ff4b4b; }
  .sub   { font-size: 20px; opacity: .8; margin-top: 4px; }
  .chip  { display:inline-block; padding: 4px 12px; margin: 3px; border-radius: 999px; font-size: 15px; font-weight: 600; }
  .l3 { background:#1f7a3a; color:#fff; } .l2 { background:#2b6cb0; color:#fff; } .l1 { background:#6b7280; color:#fff; }
  .new { outline: 3px solid #ff4b4b; }
  .lat   { font-family: ui-monospace, monospace; font-size: 13px; opacity: .85; }
  .step  { font-size: 18px; }
  h2 { margin-top: 1.2rem !important; }
</style>
""", unsafe_allow_html=True)


# ----------------------------------------------------------------------------- state helpers

def load_resume_text() -> str:
    try:
        return open("demo/resume.txt", encoding="utf-8").read()
    except FileNotFoundError:
        return ""


def cached_skills() -> list[dict]:
    try:
        return json.load(open("demo/resume_skills.json"))["skills"]
    except FileNotFoundError:
        return []


def skills_from_graph() -> list[dict]:
    return graph.candidate_skills(CID)


def signature(skills: list[dict]) -> tuple:
    return tuple(sorted((s["name"], s["level"]) for s in skills))


def get_fits(sig: tuple) -> list[dict]:
    """All 300 jobs with fit scores; cached per skill-state. Cutoff filtering is client-side -> instant slider."""
    cache = st.session_state.setdefault("fits_cache", {})
    if sig not in cache:
        cache.clear()
        cache[sig] = graph.job_fits(CID)
    return cache[sig]


def get_plan(sig: tuple, cutoff: float, budget: int) -> dict:
    cache = st.session_state.setdefault("plan_cache", {})
    key = (sig, cutoff, budget)
    if key not in cache:
        cache[key] = graph.plan_path(CID, cutoff, budget_days=budget)
    return cache[key]


def level_label(skill: str, level: int) -> str:
    return LEVEL_LABELS.get(skill, {}).get(level, f"L{level}")


def chips(skills: list[dict], highlight: set[str] = frozenset()) -> str:
    return "".join(
        f'<span class="chip l{s["level"]} {"new" if s["name"] in highlight else ""}">{s["name"]} · {level_label(s["name"], s["level"])}</span>'
        for s in skills
    )


def apply_skill(skill: str, level: int, source: str):
    """Agent memory write + bookkeeping for the 'what changed' deltas."""
    fits_before = get_fits(signature(skills_from_graph()))
    st.session_state["before"] = {"fits": fits_before, "sig": signature(skills_from_graph())}
    graph.mark_skill(CID, skill, level, source=source)
    st.session_state["highlight"] = {skill}
    st.session_state.pop("plan_cache", None)


# ----------------------------------------------------------------------------- sidebar

with st.sidebar:
    st.header("Career-Pal")
    cutoff_pct = st.slider("Minimum fit to count as *qualified*", 40, 90, 60, 5, format="%d%%")
    cutoff = cutoff_pct / 100
    budget = st.slider("Learning budget (days)", 14, 120, 45, 1)
    st.divider()
    lat = st.empty()
    st.divider()
    if st.button("Reset demo", type="secondary", width="stretch"):
        graph.set_candidate_skills(CID, [])
        for k in ("fits_cache", "plan_cache", "before", "highlight", "chat", "extract_secs", "extract_note"):
            st.session_state.pop(k, None)
        st.rerun()
    st.caption("Demo corpus: 300 synthetic Tokyo infra/cloud postings generated from role templates. "
               "Sources: METI IT HR Supply & Demand Survey (2019); Recruit Works Institute Future Predictions 2040.")


# ----------------------------------------------------------------------------- header

st.markdown('<p class="big">Career-Pal</p>', unsafe_allow_html=True)
st.markdown('<p class="sub">Japan is short <b>~790,000 IT workers by 2030</b> (METI). It is a <b>skills</b> gap, not a headcount gap. '
            'So: which skill should <i>you</i> learn next?</p>', unsafe_allow_html=True)

# ----------------------------------------------------------------------------- 1 · resume

skills = skills_from_graph()

st.header("1 · Your resume")
with st.expander("Paste resume", expanded=not skills):
    resume_text = st.text_area("Resume text", load_resume_text(), height=220, label_visibility="collapsed")
    c1, c2 = st.columns([1, 3])
    if c1.button("Analyze with ai& ⚡", type="primary", width="stretch"):
        note = ""
        try:
            with st.spinner("ai& inference · deepseek-v4-flash · extracting skills in Japan…"):
                extracted, secs = llm.extract_skills(resume_text)
            if not extracted:
                raise ValueError("no skills returned")
        except Exception as e:  # noqa: BLE001 - never let a live LLM call sink the demo
            extracted, secs, note = cached_skills(), 0.0, f"ai& unavailable ({type(e).__name__}) — loaded cached extraction"
        graph.set_candidate_skills(CID, extracted)
        st.session_state["extract_secs"] = secs
        st.session_state["extract_note"] = note
        for k in ("fits_cache", "plan_cache", "before", "highlight"):
            st.session_state.pop(k, None)
        st.rerun()
    c2.caption("Structured extraction into a 44-skill taxonomy · runs on ai& inference (open-weight DeepSeek V4 Flash, hosted in Japan — your resume never leaves the country)")

if not skills:
    st.info("Paste a resume and click **Analyze with ai&** to build your skill graph.")
    st.stop()

secs = st.session_state.get("extract_secs")
hl = st.session_state.get("highlight", set())
st.markdown(chips(skills, hl), unsafe_allow_html=True)
meta = f"**{len(skills)} skills** in your memory graph"
if secs:
    meta += f" · extracted in **{secs:.1f}s** by ai& ({llm.MODEL})"
if st.session_state.get("extract_note"):
    meta += f" · ⚠️ {st.session_state['extract_note']}"
st.caption(meta)

# ----------------------------------------------------------------------------- 2 · where you stand

sig = signature(skills)
fits = get_fits(sig)
qualified = [f for f in fits if f["fit"] >= cutoff]
n_q = len(qualified)

before = st.session_state.get("before")
delta_txt = ""
if before and before["sig"] != sig:
    n_before = sum(1 for f in before["fits"] if f["fit"] >= cutoff)
    if n_before != n_q:
        delta_txt = f' <em>({"+" if n_q > n_before else ""}{n_q - n_before})</em>'

st.header("2 · Where you stand")
st.markdown(f'<p class="big">You qualify for <em>{n_q}</em> of {TOTAL_JOBS} jobs{delta_txt}</p>'
            f'<p class="sub">at ≥ {cutoff_pct}% fit · Tokyo infra / cloud / platform roles posted in the last 30 days</p>',
            unsafe_allow_html=True)

by_role = pd.DataFrame(fits).assign(q=lambda d: d["fit"] >= cutoff).groupby("role")["q"].agg(["sum", "count"])
by_role = by_role.assign(pct=lambda d: (100 * d["sum"] / d["count"]).round()).sort_values("pct", ascending=False)
cols = st.columns([3, 2])
with cols[0]:
    df = pd.DataFrame([{
        "Fit": round(100 * f["fit"]), "Title": f["title"], "Company": f["company"], "Location": f["location"],
        "Missing": ", ".join(f'{g["s"]}{"" if g["m"] == 0 else " ↑"}' for g in f["gaps"]) or "—",
    } for f in qualified[:60]])
    st.dataframe(df, hide_index=True, width="stretch", height=330, column_config={
        "Fit": st.column_config.ProgressColumn("Fit", format="%d%%", min_value=0, max_value=100),
    })
with cols[1]:
    st.caption("Qualified share by role")
    st.dataframe(by_role.rename(columns={"sum": "qualified", "count": "jobs", "pct": "%"}), width="stretch", height=330,
                 column_config={"%": st.column_config.ProgressColumn("%", format="%d%%", min_value=0, max_value=100)})

# ----------------------------------------------------------------------------- 3 · learn next

st.header("3 · Learn next — what unlocks the most jobs?")
lb = graph.leaderboard(CID, cutoff, limit=25)
jp = next((r for r in lb if r["skill"] == "Japanese"), None)
lb = lb[:10]
if lb:
    lb_df = pd.DataFrame([{
        "Skill": f'{r["skill"]}{" (" + level_label(r["skill"], r["level"]) + ")" if r["skill"] in LEVEL_LABELS else ""}',
        "+ Jobs unlocked": r["unlocks"], "Days": r["days"], "Jobs / day": round(r["unlocks"] / r["days"], 2) if r["days"] else None,
        "Course": r["course"], "e.g.": r["examples"][0] if r["examples"] else "",
    } for r in lb])
    top = lb[0]
    vs_jp = (f' &nbsp;·&nbsp; vs. "learn Japanese first": +{jp["unlocks"]} jobs in {jp["days"]} days'
             if jp and top["skill"] != "Japanese" else "")
    st.markdown(f'<p class="step">🏆 <b>Learn {top["skill"]}</b> → <b>+{top["unlocks"]} jobs</b> in <b>{top["days"]} days</b>{vs_jp}</p>',
                unsafe_allow_html=True)
    st.dataframe(lb_df, hide_index=True, width="stretch", column_config={
        "+ Jobs unlocked": st.column_config.ProgressColumn("+ Jobs unlocked", format="%d", min_value=0, max_value=int(top["unlocks"])),
    })
else:
    st.success("No single skill would unlock more jobs at this cutoff — you're there. Raise the bar with the slider.")

# ----------------------------------------------------------------------------- 4 · fastest path

st.header(f"4 · Your fastest path — {budget}-day budget")
with st.spinner("Re-planning in Neo4j (greedy search over the skill graph)…"):
    plan = get_plan(sig, cutoff, budget)
if plan["steps"]:
    total_after = plan["base"] + plan["total_unlocked"]
    prev = None
    if before and before["sig"] != sig:
        prev = st.session_state.get("plan_cache_prev")
    st.markdown(f'<p class="big"><em>{plan["total_days"]} days</em> → +{plan["total_unlocked"]} jobs</p>'
                f'<p class="sub">{plan["base"]} → {total_after} qualified jobs at ≥ {cutoff_pct}% fit</p>', unsafe_allow_html=True)
    pcols = st.columns(len(plan["steps"]))
    for col, s in zip(pcols, plan["steps"]):
        col.metric(f'Day {s["cumulative_days"]}', s["skill"], f'+{s["unlocks"]} jobs · {s["days"]}d')
    st.session_state["plan_cache_prev"] = plan
else:
    st.info("Nothing learnable within this budget moves you past the cutoff — raise the budget or lower the bar.")

# ----------------------------------------------------------------------------- why a graph

with st.expander("Why a graph and not a vector index? Show the Cypher"):
    st.markdown("A vector index answers *'which jobs resemble my resume?'*. It cannot answer *'which single edge, if added, "
                "flips the most jobs over a threshold?'* — that is a set-cover question over explicit relationships. "
                "And when the agent learns something new, it is **one new edge**, not a re-embedding of the whole resume.")
    st.code(graph.LEADERBOARD_CYPHER.strip(), language="cypher")

# ----------------------------------------------------------------------------- 5 · agent

st.header("5 · Tell the agent what you learned")
st.caption("The agent (ai& · tool calling) writes to the Neo4j memory graph. Everything above re-plans from the new edge.")
chat = st.session_state.setdefault("chat", [])
for role, text in chat[-6:]:
    with st.chat_message(role):
        st.markdown(text)

fb1, fb2 = st.columns([1, 4])
if lb and fb1.button(f"✅ I finished {lb[0]['skill']}", help="Fallback: records the top skill without the LLM"):
    apply_skill(lb[0]["skill"], 2, source="button")
    chat.append(("user", f"I finished the {lb[0]['skill']} course."))
    chat.append(("assistant", f"Recorded **{lb[0]['skill']}** (level 2) in your memory graph. Re-planning…"))
    st.rerun()

if msg := st.chat_input("e.g. “I finished the Terraform course and built a few modules”"):
    chat.append(("user", msg))
    context = f"Candidate skills: {', '.join(s['name'] + ' L' + str(s['level']) for s in skills)}. " \
              f"Top learn-next options: {', '.join(r['skill'] + ' (+' + str(r['unlocks']) + ' jobs, ' + str(r['days']) + 'd)' for r in lb[:5])}."
    try:
        with st.spinner("ai& agent thinking…"):
            calls, text, secs = llm.agent_turn(msg, context)
        st.session_state["agent_secs"] = secs
    except Exception as e:  # noqa: BLE001
        calls, text = [], f"⚠️ ai& unavailable ({type(e).__name__}). Use the ✅ button to record the skill."
    for c in calls:
        apply_skill(c["skill"], c["level"], source="agent")
    if calls:
        text = (text + "\n\n" if text else "") + "🧠 Recorded in Neo4j: " + ", ".join(
            f'**{c["skill"]}** (level {c["level"]})' for c in calls) + f" · {secs:.1f}s on ai&"
    chat.append(("assistant", text or "(no reply)"))
    st.rerun()

# ----------------------------------------------------------------------------- latency panel (sidebar)

ms = graph.LAST_MS
lat.markdown(
    f'<div class="lat"><b>Neo4j Aura</b><br>fit scores ×300: {ms.get("job_fits", 0):.0f} ms<br>'
    f'leaderboard: {ms.get("leaderboard", 0):.0f} ms<br>memory write: {ms.get("mark_skill", 0):.0f} ms<br><br>'
    f'<b>ai& inference</b> · {llm.MODEL.split("/")[-1]}<br>'
    f'resume → skills: {(st.session_state.get("extract_secs") or 0):.1f} s<br>'
    f'agent turn: {(st.session_state.get("agent_secs") or 0):.1f} s</div>',
    unsafe_allow_html=True,
)
