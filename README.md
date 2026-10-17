# Career-Pal — what should I learn next? A graph knows.

Built solo in one day at the **Tokyo Agent Hackathon** (+81 Builders, 17 Oct 2026).

Japan is short **~790,000 IT workers by 2030** (METI, *IT Human Resources Supply & Demand Survey*, 2019). The gap is
concentrated in cloud / AI / data skills — it is a **skills** gap, not a headcount gap. Every job tool answers
*"which jobs fit me?"*. Career-Pal inverts the question: **what is the cheapest change to *me* that fits the most jobs?**

I am the user: a CKA-certified Kubernetes engineer in Tokyo. Everyone says "learn Japanese first".
The graph says: **Terraform first — +40 jobs in 10 days, vs. +18 jobs in 365 days for Japanese N2.**

## What it does (3-minute demo)

1. **Paste a resume** → ai& inference (DeepSeek V4 Flash, structured output) extracts skills into a 44-skill taxonomy → they become `HAS` edges in a Neo4j memory graph.
2. **"You qualify for 78 of 300 Tokyo jobs at ≥ 60% fit"** — fit is a weighted coverage score over each job's `REQUIRES` edges.
3. **Drag the cutoff slider** → everything recomputes live.
4. **Learn-next leaderboard** — one Cypher query answers *"which single skill, if learned, flips the most jobs over the threshold, and how many days does it cost?"*
5. **Fastest path** — greedy search over the graph on a scratch copy of the candidate: *43 days → +169 jobs*.
6. **Memory moment** — tell the agent *"I finished the Terraform course"*. ai& tool-calling → `mark_skill_acquired` → one new edge in Neo4j → leaderboard, count and path re-plan. **The graph is the agent's memory.**

## How the sponsor tools are used

**Neo4j (AuraDB)** — the knowledge graph is both the job-market model and the agent's memory:
`(:Candidate)-[:HAS {level}]->(:Skill)<-[:REQUIRES {level, weight, mandatory}]-(:Job)` and `(:Course)-[:TEACHES]->(:Skill)`.
Fit scores, the learn-next leaderboard and the learning path are Cypher queries (`graph.py`) that recompute in
~200–400 ms when the agent writes a new skill edge. Planning runs on a scratch `Candidate` so it never mutates real state.

**ai& Inference** — `deepseek-ai/deepseek-v4-flash` via the OpenAI-compatible API (`llm.py`), with `reasoning_effort="none"`
for sub-2-second turns:
- structured-output resume extraction (`json_schema` with the taxonomy as an `enum`, so no entity resolution is needed), and
- the tool-calling planning agent that records completed learning into Neo4j.
All resume text — some of the most sensitive data a person has — is processed on infrastructure in Japan.

## Why a graph and not a vector index?

A vector index answers *"which jobs resemble my resume?"*. It cannot answer *"which edge, if added, flips the most nodes over
a threshold?"* — a set-cover question over explicit relationships — and adding a skill would mean re-embedding the whole resume
instead of adding one edge. Every score here decomposes into named skills, so the match is explainable.

```cypher
// learn-next leaderboard (see graph.py for the full query)
MATCH (j:Job)-[r:REQUIRES]->(s:Skill)
OPTIONAL MATCH (:Candidate {id: $cid})-[h:HAS]->(s)
WITH j, s, r, CASE WHEN h IS NULL THEN 0.0 WHEN h.level >= r.level THEN 1.0 ELSE 0.5 END AS m
WITH j, collect({skill: s, w: r.weight, m: m}) AS reqs
WITH j, reqs, reduce(a = 0.0, x IN reqs | a + x.w * x.m) AS got, reduce(a = 0.0, x IN reqs | a + x.w) AS tot
WHERE got / tot < $cutoff
UNWIND [x IN reqs WHERE x.m < 1.0] AS gap
WITH gap.skill AS skill, j, (got + gap.w * (1.0 - gap.m)) / tot AS fit_if_learned
WHERE fit_if_learned >= $cutoff
WITH skill, count(DISTINCT j) AS unlocks
OPTIONAL MATCH (k:Course)-[:TEACHES]->(skill)
RETURN skill.name, unlocks, min(k.days) AS days ORDER BY unlocks DESC
```

## Data

The job corpus is **synthetic**: 300 Tokyo infra / cloud / platform postings generated from 10 role templates
(`skills.py`, `seed.py`) with realistic skill mixes and a ~40% share requiring Japanese N2. The graph does not care where
jobs come from — swapping the generator for a live feed (JSearch, Greenhouse, TokyoDev) is the first next step.
Learning-time estimates per skill are hand-curated. Match scores describe evidence coverage, not hiring probability.

## Run it

```bash
pip install -r requirements.txt
cp .env.example .env            # Neo4j Aura credentials + ai& API key
python check.py                 # both pipes alive?
python llm.py                   # extract + cache your resume skills (demo/resume.txt)
python seed.py --dry-run        # preview the numbers; then
python seed.py                  # seed Aura once
python -m streamlit run app.py
```

## Files

| File | Role |
|---|---|
| `skills.py` | 44-skill canonical taxonomy, learning-time estimates, courses, job role templates |
| `llm.py` | ai& client: structured skill extraction, tool-calling agent turn |
| `graph.py` | Neo4j layer: schema, seeding, fit / leaderboard / path queries, agent memory writes |
| `seed.py` | one-time synthetic job-market seed with a Python dry-run that mirrors the Cypher scoring |
| `app.py` | the Streamlit demo |
| `check.py` | pre-demo health check |

## Next

Real job feeds · Japanese-language resumes · per-skill evidence quotes · course catalog integration for real durations ·
employer view: "which of our 80%-fit candidates become 100% with one course?"
