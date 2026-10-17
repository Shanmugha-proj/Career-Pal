"""Best online courses per skill, picked by DeepSeek V4 Flash on ai& and link-verified.

  python courses.py      -> demo/courses.json  {skill: [{title, provider, url, hours, free, verified}]}

Generated once (not at demo time): every URL is fetched and kept only if it resolves; skills with no verified
link fall back to a Coursera search for the skill, so nothing in the UI points at a dead page.
"""
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote_plus

import requests

import llm
from skills import CANONICAL_SKILLS, LEVEL_LABELS

MODEL = "deepseek-ai/deepseek-v4-flash"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"}

SCHEMA = {
    "type": "object",
    "properties": {
        "courses": {
            "type": "array",
            "maxItems": 3,
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "provider": {"type": "string"},
                    "url": {"type": "string"},
                    "hours": {"type": "integer"},
                    "free": {"type": "boolean"},
                },
                "required": ["title", "provider", "url", "hours", "free"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["courses"],
    "additionalProperties": False,
}

SYSTEM = """You recommend the best online courses for working engineers.
Return the 3 best, widely recognised courses or official learning paths to reach professional, job-ready level in the skill.
Prefer official vendor learning paths and well-known providers (vendor docs/tutorials, KodeKloud, freeCodeCamp, Coursera,
edX, Udemy bestsellers, Google/AWS/Microsoft Learn, Linux Foundation, HashiCorp, Japan Foundation for Japanese).
Only return URLs you are confident exist exactly as written — canonical course or learning-path pages, no tracking params.
hours = realistic total learning hours."""


def pick(skill: str) -> list[dict]:
    target = f"{skill} ({LEVEL_LABELS[skill][2]} level)" if skill in LEVEL_LABELS else skill
    r = llm.client().chat.completions.create(
        model=MODEL, max_tokens=1200, temperature=0, reasoning_effort="none",
        response_format={"type": "json_schema", "json_schema": {"name": "courses", "schema": SCHEMA, "strict": True}},
        messages=[{"role": "system", "content": SYSTEM},
                  {"role": "user", "content": f"Skill: {target}. Audience: a cloud/infrastructure engineer in Tokyo."}],
    )
    return json.loads(r.choices[0].message.content)["courses"]


def resolves(url: str) -> bool:
    if not url.startswith("https://"):
        return False
    try:
        r = requests.get(url, headers=UA, timeout=12, allow_redirects=True, stream=True)
        ok = r.status_code < 400
        r.close()
        return ok
    except requests.RequestException:
        return False


def fallback(skill: str) -> dict:
    q = "JLPT N2 Japanese" if skill == "Japanese" else skill
    return {"title": f"Top-rated {skill} courses", "provider": "Coursera search", "free": False, "hours": 0,
            "url": f"https://www.coursera.org/search?query={quote_plus(q)}", "verified": False}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    t = time.perf_counter()
    with ThreadPoolExecutor(8) as ex:
        picks = dict(zip(CANONICAL_SKILLS, ex.map(lambda s: _safe(s) if False else pick(s), CANONICAL_SKILLS)))
    print(f"picked courses for {len(picks)} skills in {time.perf_counter() - t:.1f}s with {MODEL}")
    urls = sorted({c["url"] for cs in picks.values() for c in cs})
    t = time.perf_counter()
    with ThreadPoolExecutor(16) as ex:
        ok = dict(zip(urls, ex.map(resolves, urls)))
    print(f"verified {sum(ok.values())}/{len(urls)} links in {time.perf_counter() - t:.1f}s")
    out = {}
    for skill, cs in picks.items():
        good = [dict(c, verified=True) for c in cs if ok.get(c["url"])][:2]
        out[skill] = good or [fallback(skill)]
    json.dump(out, open("demo/courses.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("fallbacks:", [s for s, cs in out.items() if not cs[0]["verified"]])
    for s in ("Docker", "Terraform", "AWS", "CI/CD (GitLab CI/GitHub Actions)", "Japanese", "SQL"):
        print(f"  {s}: " + " | ".join(f"{c['provider']}: {c['title']} ({c['url']})" for c in out[s]))
