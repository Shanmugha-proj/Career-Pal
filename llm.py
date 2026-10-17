"""ai& inference client: structured skill extraction and the planning agent's tool-calling turn.

Runs with reasoning_effort="none" - deepseek-v4-flash is a reasoning model by default and would
otherwise spend 5-8 s thinking before every answer.
"""
import json
import os
import time

from dotenv import load_dotenv
from openai import OpenAI

from skills import CANONICAL_SKILLS

load_dotenv(".env")

MODEL = os.environ.get("AIAND_MODEL", "deepseek-ai/deepseek-v4-flash")

_client = None


def client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(base_url=os.environ["AIAND_BASE_URL"], api_key=os.environ["AIAND_API_KEY"])
    return _client


SKILLS_SCHEMA = {
    "type": "object",
    "properties": {
        "skills": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "enum": CANONICAL_SKILLS},
                    "level": {"type": "integer", "minimum": 1, "maximum": 3},
                },
                "required": ["name", "level"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["skills"],
    "additionalProperties": False,
}

EXTRACT_SYSTEM = f"""You extract a candidate's skills from a resume into a fixed taxonomy.

TAXONOMY (use these exact names, nothing else):
{chr(10).join('- ' + s for s in CANONICAL_SKILLS)}

Rules:
- Be COMPLETE: go through the whole resume and include EVERY taxonomy skill the text evidences - tools, infrastructure
  practices (bare-metal provisioning, incident RCA, networking), domain knowledge (Open RAN/5G), leadership and human languages.
- Only include skills with evidence in the text. Do not invent tools that are not mentioned.
- Use each skill name at most once.
- Levels: 1 = working knowledge / coursework, 2 = independent professional use, 3 = expert: certified, led it, or ran it at scale
  (hundreds of clusters / thousands of servers / sites counts as 'at scale').
- Certifications map to level 3 of their skill (e.g. CKA -> Kubernetes 3).
- Cisco CVIM / VIM platforms count as OpenStack. RHEL counts as Linux. ToR/VLAN/L2/L3 work counts as Networking (L2/L3).
- Server lifecycle / BIOS / firmware / RHEL installation work counts as Bare-metal Provisioning.
- RAN / Open RAN / 4G / 5G site or network work counts as Open RAN/5G.
- 'Led N engineers' / workstream lead = Team Leadership. 'Mentored' = Mentoring. RCA / postmortems = Incident Management/RCA.
- 'Japanese' levels: 1 = N3, 2 = N2 / business, 3 = N1 / native. Only include if the resume states Japanese ability.
- 'English' levels: 1 = conversational, 2 = business, 3 = fluent / native. Include if English is listed as a language."""


def extract_skills(resume_text: str) -> tuple[list[dict], float]:
    """Return ([{name, level}], seconds). Deduplicates by name keeping the highest level."""
    t = time.perf_counter()
    r = client().chat.completions.create(
        model=MODEL,
        max_tokens=2000,
        temperature=0,
        reasoning_effort="none",
        response_format={"type": "json_schema", "json_schema": {"name": "skills", "schema": SKILLS_SCHEMA, "strict": True}},
        messages=[{"role": "system", "content": EXTRACT_SYSTEM}, {"role": "user", "content": resume_text}],
    )
    data = json.loads(r.choices[0].message.content)
    best: dict[str, int] = {}
    for s in data["skills"]:
        if s["name"] in CANONICAL_SKILLS:
            best[s["name"]] = max(best.get(s["name"], 0), int(s["level"]))
    skills = [{"name": n, "level": l} for n, l in sorted(best.items(), key=lambda x: (-x[1], x[0]))]
    return skills, time.perf_counter() - t


JOB_SCHEMA = {
    "type": "object",
    "properties": {
        "requires": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "skill": {"type": "string", "enum": CANONICAL_SKILLS},
                    "level": {"type": "integer", "minimum": 1, "maximum": 3},
                    "mandatory": {"type": "boolean"},
                },
                "required": ["skill", "level", "mandatory"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["requires"],
    "additionalProperties": False,
}

JOB_SYSTEM = f"""You extract the skill requirements of a job posting into a fixed taxonomy.

TAXONOMY (use these exact names, nothing else):
{chr(10).join('- ' + s for s in CANONICAL_SKILLS)}

Rules:
- Include every taxonomy skill the posting asks for (required OR preferred), each at most once, at most 12 skills.
- mandatory = true for AT MOST 5 skills: the ones listed under required / must-have / minimum qualifications that are
  central to the role. Everything else (preferred, nice-to-have, plus, 'familiarity with') is mandatory = false.
- Levels: 1 = familiarity or exposure, 2 = professional hands-on experience, 3 = deep expertise / senior / 5+ years / lead.
- 'Japanese' is a QUALIFICATION, not the posting's language. Include it ONLY if the posting explicitly lists Japanese
  ability as required or preferred: business-level / JLPT N2 = 2, native / N1 = 3, conversational / basic / N3 = 1.
  If it says Japanese is not required, or only English is required, or it is a bilingual posting with no stated
  Japanese requirement, DO NOT include Japanese. 'English': business = 2, fluent/native = 3.
- Containers/Docker/K8s -> Docker and/or Kubernetes. Terraform/IaC -> Terraform. AWS/GCP/Azure -> the named cloud(s).
- Monitoring/observability tools -> Prometheus/Grafana, Datadog or Logging (ELK/Loki) as named. On-call/SLOs -> SRE Practices.
- Ignore generic soft skills except Team Leadership (managing/leading engineers) and Mentoring."""


def extract_job_requirements(title: str, description: str) -> list[dict]:
    """Return [{skill, level, mandatory}] for a real job posting."""
    r = client().chat.completions.create(
        model=MODEL,
        max_tokens=1500,
        temperature=0,
        reasoning_effort="none",
        response_format={"type": "json_schema", "json_schema": {"name": "job", "schema": JOB_SCHEMA, "strict": True}},
        messages=[{"role": "system", "content": JOB_SYSTEM},
                  {"role": "user", "content": f"TITLE: {title}\n\n{description[:12000]}"}],
    )
    data = json.loads(r.choices[0].message.content)
    best: dict[str, dict] = {}
    for s in data["requires"]:
        if s["skill"] in CANONICAL_SKILLS:
            prev = best.get(s["skill"])
            if not prev or s["level"] > prev["level"]:
                best[s["skill"]] = {"skill": s["skill"], "level": int(s["level"]), "mandatory": bool(s["mandatory"]) or bool(prev and prev["mandatory"])}
    return list(best.values())


AGENT_TOOLS = [{
    "type": "function",
    "function": {
        "name": "mark_skill_acquired",
        "description": "Record in the candidate's memory graph that they now have a skill, after finishing a course, project or certification.",
        "parameters": {
            "type": "object",
            "properties": {
                "skill": {"type": "string", "enum": CANONICAL_SKILLS},
                "level": {"type": "integer", "minimum": 1, "maximum": 3},
            },
            "required": ["skill", "level"],
        },
    },
}]

AGENT_SYSTEM = """You are Career-Pal's planning agent. The candidate's skills live in a Neo4j memory graph.
When the user reports completing a course, project, certification or any learning, IMMEDIATELY call mark_skill_acquired.
Never ask clarifying questions. If the level is not stated, infer it: finished a course or built something = 2,
certification or production use at work = 3. If several skills are mentioned, call the tool once per skill.
If the message is not about learning, answer in one short sentence."""


def agent_turn(user_message: str, context: str = "") -> tuple[list[dict], str, float]:
    """One agent turn. Returns (tool_calls [{skill, level}], assistant_text, seconds)."""
    t = time.perf_counter()
    msgs = [{"role": "system", "content": AGENT_SYSTEM + ("\n\nCurrent state:\n" + context if context else "")},
            {"role": "user", "content": user_message}]
    r = client().chat.completions.create(
        model=MODEL, max_tokens=1500, reasoning_effort="none", tools=AGENT_TOOLS, tool_choice="auto", messages=msgs
    )
    m = r.choices[0].message
    calls = []
    for tc in m.tool_calls or []:
        if tc.function.name == "mark_skill_acquired":
            args = json.loads(tc.function.arguments)
            if args.get("skill") in CANONICAL_SKILLS:
                calls.append({"skill": args["skill"], "level": int(args.get("level", 2))})
    return calls, (m.content or "").strip(), time.perf_counter() - t


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    text = open("demo/resume.txt", encoding="utf-8").read()
    skills, secs = extract_skills(text)
    print(f"extracted {len(skills)} skills in {secs:.1f}s")
    for s in skills:
        print(f"  {s['level']}  {s['name']}")
    json.dump({"skills": skills, "seconds": round(secs, 2), "model": MODEL}, open("demo/resume_skills.json", "w"), indent=2)
    print("cached -> demo/resume_skills.json")
