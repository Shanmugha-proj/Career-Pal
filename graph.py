"""Neo4j access layer: the knowledge graph is both the job market model and the agent's memory.

Schema
  (:Candidate {id})-[:HAS {level, source, acquired_at}]->(:Skill {name})
  (:Job {id, title, company, location, posted_days_ago, role})-[:REQUIRES {level, weight, mandatory}]->(:Skill)
  (:Course {id, name, days, to_level})-[:TEACHES]->(:Skill)

Fit score for a (candidate, job) = sum(weight * match) / sum(weight) over the job's requirements, where
match = 1.0 if the candidate has the skill at the required level, 0.5 if at a lower level, 0 if missing.
"""
import os
import time
from contextlib import contextmanager

from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv(".env")

_driver = None
LAST_MS: dict[str, float] = {}  # query name -> last round-trip in ms (for the UI latency labels)


def driver():
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(os.environ["NEO4J_URI"], auth=(os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"]),
                                       notifications_min_severity="OFF")
    return _driver


def run(name: str, cypher: str, **params) -> list[dict]:
    t = time.perf_counter()
    recs, _, _ = driver().execute_query(cypher, parameters_=params, database_=os.environ.get("NEO4J_DATABASE"))
    LAST_MS[name] = 1000 * (time.perf_counter() - t)
    return [r.data() for r in recs]


# --------------------------------------------------------------------------- schema & seeding

def init_schema():
    for c in [
        "CREATE CONSTRAINT skill_name IF NOT EXISTS FOR (s:Skill) REQUIRE s.name IS UNIQUE",
        "CREATE CONSTRAINT job_id IF NOT EXISTS FOR (j:Job) REQUIRE j.id IS UNIQUE",
        "CREATE CONSTRAINT candidate_id IF NOT EXISTS FOR (c:Candidate) REQUIRE c.id IS UNIQUE",
        "CREATE CONSTRAINT course_id IF NOT EXISTS FOR (k:Course) REQUIRE k.id IS UNIQUE",
    ]:
        run("schema", c)


def wipe_all():
    run("wipe", "MATCH (n) DETACH DELETE n")


def upsert_skills(names: list[str]):
    run("upsert_skills", "UNWIND $names AS n MERGE (:Skill {name: n})", names=names)


def upsert_courses(courses: list[dict]):
    run("upsert_courses", """
        UNWIND $courses AS c
        MERGE (k:Course {id: c.id}) SET k.name = c.name, k.days = c.days, k.to_level = c.to_level
        WITH k, c MATCH (s:Skill {name: c.skill}) MERGE (k)-[:TEACHES]->(s)
    """, courses=courses)


def upsert_jobs(jobs: list[dict]):
    """jobs: [{id, title, company, location, posted_days_ago, role, requires: [{skill, level, mandatory}]}]"""
    run("upsert_jobs", """
        UNWIND $jobs AS j
        MERGE (job:Job {id: j.id})
        SET job.title = j.title, job.company = j.company, job.location = j.location,
            job.posted_days_ago = j.posted_days_ago, job.role = j.role,
            job.source = coalesce(j.source, 'synthetic'), job.url = coalesce(j.url, ''), job.board = coalesce(j.board, ''),
            job.other_required = coalesce(j.other_required, 0), job.other_requirements = coalesce(j.other_requirements, [])
        WITH job, j
        UNWIND j.requires AS r
        MATCH (s:Skill {name: r.skill})
        MERGE (job)-[q:REQUIRES]->(s)
        SET q.level = r.level, q.mandatory = r.mandatory, q.weight = CASE WHEN r.mandatory THEN 2.0 ELSE 1.0 END
    """, jobs=jobs)


def counts() -> dict:
    return run("counts", "RETURN count{ (:Job) } AS jobs, count{ (:Skill) } AS skills, count{ (:Course) } AS courses, "
                          "count{ ()-[:REQUIRES]->() } AS requires")[0]


# --------------------------------------------------------------------------- candidate memory

def set_candidate_skills(cid: str, skills: list[dict], source: str = "resume"):
    """Replace the candidate's skill edges. skills: [{name, level}]"""
    run("set_candidate_skills", """
        MERGE (c:Candidate {id: $cid})
        WITH c OPTIONAL MATCH (c)-[h:HAS]->() DELETE h
        WITH DISTINCT c
        UNWIND $skills AS s
        MATCH (sk:Skill {name: s.name})
        MERGE (c)-[h:HAS]->(sk) SET h.level = s.level, h.source = $source, h.acquired_at = datetime()
    """, cid=cid, skills=skills, source=source)


def mark_skill(cid: str, skill: str, level: int, source: str = "agent"):
    """The agent's single write: the graph remembers a newly acquired skill."""
    return run("mark_skill", """
        MATCH (c:Candidate {id: $cid}), (s:Skill {name: $skill})
        MERGE (c)-[h:HAS]->(s)
        SET h.level = CASE WHEN coalesce(h.level, 0) > $level THEN h.level ELSE $level END,
            h.source = $source, h.acquired_at = datetime()
        RETURN s.name AS skill, h.level AS level
    """, cid=cid, skill=skill, level=level, source=source)


def candidate_skills(cid: str) -> list[dict]:
    return run("candidate_skills", """
        MATCH (:Candidate {id: $cid})-[h:HAS]->(s:Skill)
        RETURN s.name AS name, h.level AS level, h.source AS source ORDER BY level DESC, name
    """, cid=cid)


# --------------------------------------------------------------------------- the three demo queries

FIT_CYPHER = """
MATCH (j:Job)-[r:REQUIRES]->(s:Skill) WHERE NOT s.name IN $soft      // soft skills never count toward fit
OPTIONAL MATCH (:Candidate {id: $cid})-[h:HAS]->(s)
WITH j, s, r, CASE WHEN h IS NULL THEN 0.0 WHEN h.level >= r.level THEN 1.0 ELSE 0.5 END AS m
// required skills outside the taxonomy (e.g. C/C++, RTOS) count as unmet mandatory requirements (weight 1.0 each)
WITH j, sum(r.weight * m) / (sum(r.weight) + 1.0 * coalesce(j.other_required, 0)) AS fit,
     [x IN collect({s: s.name, m: m, lvl: r.level, mand: r.mandatory}) WHERE x.m = 1.0 | x.s] AS matched,
     [x IN collect({s: s.name, m: m, lvl: r.level, mand: r.mandatory}) WHERE x.m < 1.0 | x] AS gaps
RETURN j.id AS id, j.title AS title, j.company AS company, j.location AS location, j.role AS role,
       j.posted_days_ago AS posted_days_ago, j.source AS source, j.url AS url, fit, matched, gaps,
       coalesce(j.other_requirements, []) AS other
ORDER BY fit DESC, j.title
"""


def job_fits(cid: str) -> list[dict]:
    """Every job with its fit score for the candidate. Cutoff filtering happens client-side (instant slider)."""
    return run("job_fits", FIT_CYPHER, cid=cid, soft=SOFT_SKILLS)


LEADERBOARD_CYPHER = """
MATCH (j:Job)-[r:REQUIRES]->(s:Skill) WHERE NOT s.name IN $soft
OPTIONAL MATCH (:Candidate {id: $cid})-[h:HAS]->(s)
WITH j, s, r, CASE WHEN h IS NULL THEN 0.0 WHEN h.level >= r.level THEN 1.0 ELSE 0.5 END AS m
WITH j, collect({skill: s, w: r.weight, m: m, lvl: r.level}) AS reqs
WITH j, reqs, reduce(a = 0.0, x IN reqs | a + x.w * x.m) AS got,
              reduce(a = 0.0, x IN reqs | a + x.w) + 1.0 * coalesce(j.other_required, 0) AS tot   // + uncovered must-haves
WHERE got / tot < $cutoff                                  // jobs the candidate does NOT yet qualify for
UNWIND [x IN reqs WHERE x.m < 1.0 AND NOT x.skill.name IN $exclude] AS gap   // each skill they lack (soft skills excluded)
WITH gap.skill AS skill, gap.lvl AS lvl, j, (got + gap.w * (1.0 - gap.m)) / tot AS fit_if_learned
WHERE fit_if_learned >= $cutoff                             // learning this ONE skill crosses the line
WITH skill, max(lvl) AS level, count(DISTINCT j) AS unlocks, collect(DISTINCT j.title)[..3] AS examples
OPTIONAL MATCH (k:Course)-[:TEACHES]->(skill)
WITH skill, level, unlocks, min(k.days) AS days, head(collect(k.name)) AS course, examples
RETURN skill.name AS skill, level, unlocks, days, course, examples,
       round(toFloat(unlocks) / days, 2) AS jobs_per_day            // the cheapest edge, not the biggest
ORDER BY jobs_per_day DESC, unlocks DESC
LIMIT $limit
"""


SOFT_SKILLS = ["Technical Documentation", "Agile/Scrum", "Mentoring", "English"]   # never count toward fit or unlocks


def leaderboard(cid: str, cutoff: float, limit: int = 10) -> list[dict]:
    """'Learn X -> unlock N more jobs in D days' - the question a vector index cannot answer."""
    return run("leaderboard", LEADERBOARD_CYPHER, cid=cid, cutoff=cutoff, limit=limit, exclude=SOFT_SKILLS, soft=SOFT_SKILLS)


def qualify_count(cid: str, cutoff: float) -> dict:
    return run("qualify_count", """
        MATCH (j:Job)-[r:REQUIRES]->(s:Skill) WHERE NOT s.name IN $soft
        OPTIONAL MATCH (:Candidate {id: $cid})-[h:HAS]->(s)
        WITH j, r, CASE WHEN h IS NULL THEN 0.0 WHEN h.level >= r.level THEN 1.0 ELSE 0.5 END AS m
        WITH j, sum(r.weight * m) / (sum(r.weight) + 1.0 * coalesce(j.other_required, 0)) AS fit
        RETURN count(*) AS total, sum(CASE WHEN fit >= $cutoff THEN 1 ELSE 0 END) AS qualify
    """, cid=cid, cutoff=cutoff, soft=SOFT_SKILLS)[0]


# --------------------------------------------------------------------------- learning path (greedy, on a scratch copy)

@contextmanager
def scratch_candidate(cid: str):
    """Clone the candidate's memory into '<cid>:plan' so planning never mutates real state."""
    sid = f"{cid}:plan"
    run("scratch_create", """
        MATCH (c:Candidate {id: $cid})-[h:HAS]->(s)
        MERGE (p:Candidate {id: $sid})
        MERGE (p)-[ph:HAS]->(s) SET ph.level = h.level
    """, cid=cid, sid=sid)
    try:
        yield sid
    finally:
        run("scratch_drop", "MATCH (p:Candidate {id: $sid}) DETACH DELETE p", sid=sid)


def plan_path(cid: str, cutoff: float, budget_days: int = 60, max_steps: int = 5) -> dict:
    """Greedy: repeatedly learn the skill with the best jobs-unlocked-per-day that fits the remaining budget."""
    steps, spent = [], 0
    base = qualify_count(cid, cutoff)["qualify"]
    with scratch_candidate(cid) as sid:
        before = base
        for _ in range(max_steps):
            options = [o for o in leaderboard(sid, cutoff, limit=25) if o["days"] and spent + o["days"] <= budget_days]
            if not options:
                break
            best = max(options, key=lambda o: (o["unlocks"] / o["days"], o["unlocks"]))
            mark_skill(sid, best["skill"], max(2, best["level"] or 2), source="plan")
            spent += best["days"]
            after = qualify_count(sid, cutoff)["qualify"]
            steps.append({"skill": best["skill"], "days": best["days"], "unlocks": after - before,
                          "cumulative_days": spent, "cumulative_jobs": after - base, "course": best["course"]})
            before = after
    return {"base": base, "steps": steps, "total_days": spent, "total_unlocked": (before - base) if steps else 0}
