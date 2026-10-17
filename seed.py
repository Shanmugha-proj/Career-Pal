"""One-time seed of the demo job market into Neo4j.

  python seed.py --dry-run      generate in memory and preview the demo numbers against demo/resume_skills.json
  python seed.py                seed Aura (fails if the DB is not empty)
  python seed.py --reset        wipe the DB first, then seed

The corpus is synthetic: 300 Tokyo infra/cloud postings generated from role templates in skills.py.
"""
import argparse
import json
import random
from collections import Counter

from skills import CANONICAL_SKILLS, COMPANIES, COURSES, LEARN_DAYS, ROLE_TEMPLATES, SENIORITY_PREFIXES

SEED = 42


def generate_jobs(seed: int = SEED) -> list[dict]:
    rng = random.Random(seed)
    jobs, n = [], 0
    for tpl in ROLE_TEMPLATES:
        for _ in range(tpl["count"]):
            n += 1
            reqs = {s: (lvl, mand) for s, lvl, mand in tpl["core"]}
            for s, lvl, p in tpl["optional"]:
                if rng.random() < p:
                    reqs[s] = (lvl, False)
            if rng.random() < tpl["jp"]:
                reqs["Japanese"] = (2, rng.random() < 0.5)  # N2 required; sometimes a hard requirement
            elif rng.random() < 0.25:
                reqs["Japanese"] = (1, False)  # N3 nice-to-have
            if rng.random() < 0.6:
                reqs["English"] = (2, False)
            company, ward = rng.choice(COMPANIES)
            jobs.append({
                "id": f"job-{n:03d}",
                "title": rng.choice(SENIORITY_PREFIXES) + tpl["title"],
                "company": company,
                "location": f"{ward}, Tokyo" if ward not in ("Kawasaki", "Yokohama") else f"{ward}, Kanagawa",
                "posted_days_ago": rng.randint(1, 30),
                "role": tpl["title"],
                "requires": [{"skill": s, "level": lvl, "mandatory": mand} for s, (lvl, mand) in reqs.items()],
            })
    rng.shuffle(jobs)
    return jobs


# ---- pure-python mirror of the Cypher scoring, for fast tuning without round-trips -------------

def fit(job: dict, have: dict[str, int]) -> float:
    got = tot = 0.0
    for r in job["requires"]:
        w = 2.0 if r["mandatory"] else 1.0
        h = have.get(r["skill"])
        m = 0.0 if h is None else (1.0 if h >= r["level"] else 0.5)
        got += w * m
        tot += w
    return got / tot


def leaderboard_py(jobs, have, cutoff):
    unlocks = Counter()
    for j in jobs:
        f = fit(j, have)
        if f >= cutoff:
            continue
        tot = sum(2.0 if r["mandatory"] else 1.0 for r in j["requires"])
        for r in j["requires"]:
            h = have.get(r["skill"])
            m = 0.0 if h is None else (1.0 if h >= r["level"] else 0.5)
            if m < 1.0:
                w = 2.0 if r["mandatory"] else 1.0
                if f + w * (1.0 - m) / tot >= cutoff:
                    unlocks[r["skill"]] += 1
    return unlocks.most_common(10)


def preview(jobs: list[dict]):
    print(f"{len(jobs)} jobs | roles: {dict(Counter(j['role'] for j in jobs))}")
    jp2 = sum(1 for j in jobs if any(r['skill'] == 'Japanese' and r['level'] >= 2 for r in j['requires']))
    print(f"Japanese N2+ required by {jp2} jobs ({100*jp2/len(jobs):.0f}%)")
    skill_freq = Counter(r["skill"] for j in jobs for r in j["requires"])
    print("most demanded skills:", skill_freq.most_common(12))
    try:
        have = {s["name"]: s["level"] for s in json.load(open("demo/resume_skills.json"))["skills"]}
    except FileNotFoundError:
        print("no demo/resume_skills.json yet - run python llm.py to cache the candidate's skills")
        return
    print(f"\ncandidate has {len(have)} skills: {have}")
    for cutoff in (0.5, 0.6, 0.7, 0.8):
        q = sum(1 for j in jobs if fit(j, have) >= cutoff)
        print(f"  cutoff {int(cutoff*100)}%: qualifies for {q:3d} / {len(jobs)}")
    for cutoff in (0.6, 0.7):
        print(f"\nleaderboard @ {int(cutoff*100)}%  (skill, +jobs, days):")
        for s, n in leaderboard_py(jobs, have, cutoff):
            print(f"  {s:38s} +{n:3d}   {LEARN_DAYS[s]:4d} days")


def seed(reset: bool):
    import graph

    jobs = generate_jobs()
    if reset:
        print("wiping database ...")
        graph.wipe_all()
    elif graph.counts()["jobs"]:
        raise SystemExit("database is not empty - rerun with --reset to wipe and reseed")
    graph.init_schema()
    graph.upsert_skills(CANONICAL_SKILLS)
    graph.upsert_courses(COURSES)
    for i in range(0, len(jobs), 100):
        graph.upsert_jobs(jobs[i:i + 100])
    try:
        skills = json.load(open("demo/resume_skills.json"))["skills"]
        graph.set_candidate_skills("demo", skills)
        print(f"candidate 'demo' seeded with {len(skills)} skills from demo/resume_skills.json")
    except FileNotFoundError:
        pass
    print("seeded:", graph.counts())


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--reset", action="store_true")
    a = ap.parse_args()
    if a.dry_run:
        preview(generate_jobs())
    else:
        seed(a.reset)
