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


TOTAL = 300
TITLE_TO_ROLE = [
    (r"sre|reliability", "Site Reliability Engineer"), (r"platform", "Platform Engineer (Kubernetes)"),
    (r"devops", "DevOps Engineer"), (r"network", "Telecom Cloud Engineer (Open RAN / 5G Core)"),
    (r"security", "Cloud Security Engineer"), (r"data ?cent|datacenter", "Data Center Infrastructure Engineer"),
    (r"data|database|dbre|spark|analytics", "Data Platform Engineer"), (r"manager|lead|head", "Infrastructure Team Lead"),
    (r"backend|back-end|software|product engineer|forward deployed", "Backend Engineer (Go/Python)"),
    (r"cloud|infra|systems|solution|support|field|technical account|it ", "Cloud Infrastructure Engineer"),
]


def role_for(title: str) -> str:
    import re
    t = title.lower()
    for pat, role in TITLE_TO_ROLE:
        if re.search(pat, t):
            return role
    return "Cloud Infrastructure Engineer"


def load_real_jobs() -> list[dict]:
    """Real postings pulled from public job-board APIs and extracted with ai& (python real_jobs.py extract)."""
    try:
        raw = json.load(open("demo/real_jobs.json", encoding="utf-8"))
    except FileNotFoundError:
        return []
    import re
    non_software = re.compile(r"propulsion|spacecraft|mechanical|tire|electrical|facility|facilities|GNC|guidance|thermal|"
                              r"structural|manufacturing|hardware|chiplet|physical design|verification engineer|field service", re.I)
    jobs = []
    for i, j in enumerate(raw, 1):
        if non_software.search(j["title"]):
            continue
        jobs.append({
            "id": f"real-{i:03d}", "title": j["title"].strip(), "company": j["company"], "location": j["location"] or "Tokyo, Japan",
            "posted_days_ago": 7, "role": role_for(j["title"]), "source": "real", "url": j.get("url", ""),
            "board": j.get("board", ""), "requires": j["requires"],
            "other_requirements": j.get("other_requirements", []), "other_required": len(j.get("other_requirements", [])),
        })
    return jobs


def generate_jobs(seed: int = SEED, n_synthetic: int | None = None) -> list[dict]:
    import math
    rng = random.Random(seed)
    jobs, n = [], 0
    scale = 1.0 if n_synthetic is None else n_synthetic / TOTAL
    for tpl in ROLE_TEMPLATES:
        for _ in range(math.ceil(tpl["count"] * scale)):
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
                "source": "synthetic", "url": "", "board": "",
                "requires": [{"skill": s, "level": lvl, "mandatory": mand} for s, (lvl, mand) in reqs.items()],
            })
    rng.shuffle(jobs)
    return jobs if n_synthetic is None else jobs[:n_synthetic]


INFRA_RE = __import__("re").compile(r"platform|infra|sre|reliability|devops|cloud|kubernetes|network|security|data ?cent|"
                                     r"systems? engineer|linux|storage|database|dbre|observab", __import__("re").I)


INFRA_SKILLS = {"Kubernetes", "Docker", "Helm", "OpenStack", "AWS", "GCP", "Azure", "Terraform", "Ansible", "Linux",
                "Bare-metal Provisioning", "Networking (L2/L3)", "Storage (Ceph/SAN)", "Virtualization (VMware/KVM)",
                "CI/CD (GitLab CI/GitHub Actions)", "GitOps (ArgoCD/Flux)", "Prometheus/Grafana", "Logging (ELK/Loki)", "Datadog",
                "Incident Management/RCA", "SRE Practices (SLOs/On-call)", "Cloud Security/IAM", "Secrets Management (Vault)",
                "Open RAN/5G", "Telecom Core Networks", "Bash", "Service Mesh (Istio)", "OpenShift"}


def relevance(job: dict) -> float:
    """How infra/cloud/platform-relevant a real posting is: title keywords + share of infra skills required."""
    infra = sum(1 for r in job["requires"] if r["skill"] in INFRA_SKILLS)
    return (3 if INFRA_RE.search(job["title"]) else 0) + infra + 0.5 * sum(1 for r in job["requires"] if r["skill"] in INFRA_SKILLS and r["mandatory"])


def build_corpus(max_real: int = 150, total: int = TOTAL) -> list[dict]:
    """Real jobs first (most infra-relevant first, up to max_real), synthetic fills the remainder (0 if total == max_real)."""
    real = load_real_jobs()
    real.sort(key=lambda j: (-relevance(j), j["id"]))
    real = real[:max_real]
    synthetic = generate_jobs(n_synthetic=total - len(real))
    jobs = real + synthetic
    random.Random(SEED).shuffle(jobs)
    return jobs


# ---- pure-python mirror of the Cypher scoring, for fast tuning without round-trips -------------

def fit(job: dict, have: dict[str, int]) -> float:
    got, tot = 0.0, 1.0 * job.get("other_required", 0)   # uncovered must-haves count as unmet mandatory requirements
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
    src = Counter(j["source"] for j in jobs)
    print(f"{len(jobs)} jobs | {src.get('real', 0)} real + {src.get('synthetic', 0)} synthetic | roles: {dict(Counter(j['role'] for j in jobs))}")
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


def seed(reset: bool, max_real: int = 150, total: int = TOTAL):
    import graph

    jobs = build_corpus(max_real, total)
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
    ap.add_argument("--real", type=int, default=150, help="max real postings to include")
    ap.add_argument("--total", type=int, default=TOTAL)
    a = ap.parse_args()
    if a.dry_run:
        preview(build_corpus(a.real, a.total))
    else:
        seed(a.reset, a.real, a.total)
