"""Pull REAL Tokyo/Japan engineering postings from public Greenhouse / Lever job-board APIs,
then extract their skill requirements with ai& into the canonical taxonomy.

  python real_jobs.py probe      # which boards have Japan roles? (no LLM)
  python real_jobs.py fetch      # save matching postings -> demo/real_jobs_raw.json
  python real_jobs.py extract    # ai& structured extraction -> demo/real_jobs.json (used by seed.py)
"""
import html
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

GREENHOUSE = [
    # global infra/cloud companies with Tokyo offices
    "datadog", "hashicorp", "cloudflare", "stripe", "elastic", "mongodb", "databricks", "gitlab", "canonical",
    "transferwise", "fastly", "pagerduty", "okta", "twilio", "zendesk", "confluent", "grafanalabs", "newrelic",
    "dynatrace", "akamai", "digitalocean", "cockroachlabs", "pingcap", "snyk", "crowdstrike", "zscaler",
    "paloaltonetworks", "nutanix", "rubrik", "purestorage", "coinbase", "circle", "chainalysis", "airbnb",
    "doordash", "indeed", "woven-by-toyota", "wovenbytoyota", "woven", "paypay", "smartnews", "mercari", "autify",
    "mujin", "tier4", "rapyutarobotics", "ubie", "kakehashi", "shippio", "treasuredata", "sansan", "moneyforward",
    "bitflyer", "lycorp", "line", "preferrednetworks", "cadence", "arm", "sumologic", "splunk", "f5", "arista",
    "scylladb", "redis", "vercel", "netlify", "snowflake", "atlassian", "github", "wise", "revolut", "nium",
    "anthropic", "openai", "scaleai", "cohere", "huggingface", "weightsandbiases",
    # discovered via site: searches for Tokyo/Japan postings
    "6sense", "adyen", "alpaca", "andurilindustries", "appier", "appliedintuition", "axs", "blacksky", "boku", "boxinc",
    "coupanginternal", "cresta", "crunchyroll", "deepmind", "dialpad", "figma", "gatikaiinc", "hyphenconnect", "jamf",
    "lazarusenterprises", "manychat", "moon", "neo4j", "paypaycard", "point72", "queracomputinginc", "route06",
    "sambanovasystems", "sayari", "siei", "spacex", "speechify", "tenstorrent", "wantedly", "waymo", "wayve", "wework", "xai",
]
LEVER = ["palantir", "mercari", "smartnews", "paypay", "moneyforward", "ubie", "kakehashi", "shippio", "tier4", "mujin",
         "woven", "autify", "plaid", "netlify", "mistral", "figma", "notion", "whatnot", "rippling", "brex",
         "binance", "cic", "csit", "extremenetworks", "ispace-inc", "limitbreak", "matchgroup", "mujininc", "shakudo",
         "verygoodsecurity", "woven-by-toyota", "xsolla", "yuno", "zilliz"]
SMARTRECRUITERS = ["AFRY", "ApplusIDIADA1", "aristanetworks", "BoschGroup", "continental", "HitachiSolutions", "IFS1",
                   "KeywordsStudios", "LingoNetwork", "mirantis", "Nagarro1", "nearmap", "NECSWS", "nextdc", "psicro",
                   "RenesasElectronics", "santen", "servicenow", "tomra", "utac", "wabtec", "Rakuten", "Visa", "Ubisoft"]
# Workday tenants: (tenant, wdN, site)
WORKDAY = [("rakuten", "wd1", "RakutenInc"), ("rakuten", "wd1", "RakutenMobile"), ("rakuten", "wd1", "RakutenSymphony"),
           ("rakuten", "wd1", "RakutenSymphonyJapan"), ("rakuten", "wd1", "RakutenAsia"), ("dxctechnology", "wd1", "DXCJobs"),
           ("nvidia", "wd5", "NVIDIAExternalCareerSite"), ("salesforce", "wd12", "External_Career_Site"),
           ("adobe", "wd5", "external_experienced"), ("snowflake", "wd5", "Snowflake_Careers"), ("servicenow", "wd1", "ServiceNow"),
           ("autodesk", "wd1", "Ext"), ("workday", "wd5", "Workday"), ("hitachi", "wd1", "hitachi"), ("intel", "wd1", "External"),
           ("amd", "wd1", "External"), ("redhat", "wd5", "jobs"), ("broadcom", "wd1", "External_Career"),
           ("equinix", "wd1", "Equinix_Careers"), ("akamai", "wd1", "Akamai_Careers"), ("netapp", "wd1", "NetApp_Careers"),
           ("nutanix", "wd1", "Nutanix_Careers"), ("paloaltonetworks", "wd1", "PaloAltoNetworks_Careers")]

JP_RE = re.compile(r"tokyo|japan|東京|日本|osaka|kanagawa|yokohama|apac.*japan|\bJP\b", re.I)
TITLE_RE = re.compile(r"platform|infrastructure|infra\b|\bsre\b|site reliability|devops|cloud|kubernetes|network|"
                      r"systems? engineer|security engineer|data ?cent|solutions? (architect|engineer)|backend|back-end|"
                      r"software engineer|production engineer|reliability|observability|database|storage|linux|"
                      r"technical account|support engineer|customer engineer|field engineer|"
                      r"インフラ|クラウド|プラットフォーム|ネットワーク|サーバ|基盤|運用|セキュリティ|エンジニア", re.I)


def strip_html(s: str) -> str:
    s = html.unescape(s or "")
    s = re.sub(r"<(br|/p|/li|/div|/h\d)[^>]*>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"[ \t\xa0]+", " ", s)
    return re.sub(r"\n\s*\n+", "\n", s).strip()


def fetch_greenhouse(token: str) -> list[dict]:
    r = requests.get(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs", params={"content": "true"}, timeout=20)
    if r.status_code != 200:
        return []
    out = []
    for j in r.json().get("jobs", []):
        loc = (j.get("location") or {}).get("name", "") or " ".join(o.get("name", "") for o in j.get("offices", []))
        out.append({"source": "greenhouse", "board": token, "title": j["title"], "company": token, "location": loc,
                    "url": j["absolute_url"], "description": strip_html(j.get("content", "")), "updated": j.get("updated_at", "")})
    return out


def fetch_lever(company: str) -> list[dict]:
    r = requests.get(f"https://api.lever.co/v0/postings/{company}", params={"mode": "json"}, timeout=20)
    if r.status_code != 200:
        return []
    out = []
    for j in r.json():
        cats = j.get("categories") or {}
        desc = j.get("descriptionPlain", "") + "\n" + "\n".join(
            l.get("text", "") + "\n" + strip_html(l.get("content", "")) for l in j.get("lists", []))
        out.append({"source": "lever", "board": company, "title": j["text"], "company": company,
                    "location": cats.get("location", ""), "url": j["hostedUrl"], "description": desc.strip(),
                    "updated": j.get("createdAt", "")})
    return out


WORKABLE = ["mercari", "smartnews", "hennge", "kyash", "zeals", "cookpad", "sakana", "bitkey", "telexistence", "pksha", "abeja",
            "legalon", "smarthr", "freee", "sansan", "cybozu", "estie", "luup", "timee", "andpad", "caddi", "mujin-corp",
            "rapyuta", "tier-iv", "shippio", "ubie", "kakehashi", "autify-inc", "wovenbytoyota", "paypay-corp",
            "exotec", "rapyuta-robotics", "sakana-ai", "ai-robot-association", "polymer-capital-japan"]
ASHBY = ["openai", "notion", "sakana-ai", "sakana", "scale", "elevenlabs", "perplexity", "supabase", "cursor", "anysphere",
         "vercel", "deel", "rippling", "posthog", "retool", "cohere", "glean", "writer", "sierra", "harvey", "mercor",
         "woven-by-toyota", "paypay", "smartnews", "mercari", "autify", "mujin", "tier4",
         "aiand", "applied", "bjakcareer", "carnot-ai", "cerebras", "clickhouse", "crusoe", "liquid-ai", "neuralconcept",
         "sierra-jp", "signoz", "skydio", "stack-infrastructure-apac-pte-ltd", "tailor", "twelve-labs", "wayve"]


def fetch_smartrecruiters(company: str) -> list[dict]:
    r = requests.get(f"https://api.smartrecruiters.com/v1/companies/{company}/postings", params={"limit": 100}, timeout=20)
    if r.status_code != 200:
        return []
    out = []
    for p in r.json().get("content", []):
        loc = p.get("location") or {}
        loc_s = ", ".join(x for x in (loc.get("city", ""), loc.get("region", ""), loc.get("country", "")) if x)
        if not JP_RE.search(loc_s + " " + p.get("name", "")):
            continue
        d = requests.get(f"https://api.smartrecruiters.com/v1/companies/{company}/postings/{p['id']}", timeout=20)
        if d.status_code != 200:
            continue
        sections = (d.json().get("jobAd") or {}).get("sections") or {}
        desc = "\n".join(strip_html(s.get("text", "")) for s in sections.values() if isinstance(s, dict))
        out.append({"source": "smartrecruiters", "board": company, "title": p["name"], "company": company, "location": loc_s,
                    "url": p.get("ref", "").replace("api.smartrecruiters.com/v1/companies", "jobs.smartrecruiters.com") or
                           f"https://jobs.smartrecruiters.com/{company}/{p['id']}",
                    "description": desc, "updated": p.get("releasedDate", "")})
    return out


def fetch_workday(tenant: str, wd: str, site: str) -> list[dict]:
    base = f"https://{tenant}.{wd}.myworkdayjobs.com/wday/cxs/{tenant}/{site}"
    out, offset = [], 0
    hdr = {"Accept": "application/json", "Content-Type": "application/json"}
    while offset < 200:
        r = requests.post(f"{base}/jobs", json={"appliedFacets": {}, "limit": 20, "offset": offset, "searchText": "Tokyo"},
                          headers=hdr, timeout=25)
        if r.status_code != 200:
            break
        posts = r.json().get("jobPostings", [])
        if not posts:
            break
        for p in posts:
            loc = p.get("locationsText", "")
            if not JP_RE.search(loc) or not TITLE_RE.search(p.get("title", "")):
                continue
            d = requests.get(f"{base}{p['externalPath']}", headers=hdr, timeout=25)
            if d.status_code != 200:
                continue
            info = d.json().get("jobPostingInfo") or {}
            out.append({"source": "workday", "board": f"{tenant}/{site}", "title": info.get("title", p["title"]),
                        "company": tenant, "location": info.get("location", loc),
                        "url": info.get("externalUrl") or f"https://{tenant}.{wd}.myworkdayjobs.com/{site}{p['externalPath']}",
                        "description": strip_html(info.get("jobDescription", "")), "updated": info.get("startDate", "")})
        offset += 20
    return out


def fetch_workable(account: str) -> list[dict]:
    r = requests.get(f"https://apply.workable.com/api/v1/widget/accounts/{account}", params={"details": "true"}, timeout=20)
    if r.status_code != 200:
        return []
    out = []
    for j in r.json().get("jobs", []):
        loc = ", ".join(x for x in (j.get("city", ""), j.get("state", ""), j.get("country", "")) if x)
        desc = strip_html((j.get("description") or "") + "\n" + (j.get("requirements") or "") + "\n" + (j.get("benefits") or ""))
        out.append({"source": "workable", "board": account, "title": j["title"], "company": account, "location": loc,
                    "url": j.get("url") or j.get("application_url", ""), "description": desc, "updated": j.get("published_on", "")})
    return out


def fetch_ashby(org: str) -> list[dict]:
    r = requests.get(f"https://api.ashbyhq.com/posting-api/job-board/{org}", params={"includeCompensation": "false"}, timeout=20)
    if r.status_code != 200:
        return []
    out = []
    for j in r.json().get("jobs", []):
        if not j.get("isListed", True):
            continue
        loc = j.get("location", "") or ", ".join(a.get("location", "") for a in j.get("secondaryLocations", []))
        out.append({"source": "ashby", "board": org, "title": j["title"], "company": org, "location": loc,
                    "url": j.get("jobUrl") or j.get("applyUrl", ""), "description": strip_html(j.get("descriptionHtml", "")),
                    "updated": j.get("publishedAt", "")})
    return out


JSEARCH_QUERIES = [
    "Kubernetes engineer Tokyo", "Site Reliability Engineer Tokyo", "Platform Engineer Tokyo", "DevOps Engineer Tokyo",
    "Cloud Infrastructure Engineer Tokyo", "Infrastructure Engineer Tokyo", "Network Engineer Tokyo",
    "Cloud Engineer AWS Tokyo", "SRE Japan", "Data Center Engineer Tokyo", "Linux Systems Engineer Tokyo",
    "Backend Engineer Go Tokyo", "Security Engineer cloud Tokyo", "Telecom cloud engineer 5G Japan",
    "インフラエンジニア 東京", "SRE 東京",
]
JSEARCH_QUERIES_2 = [
    "クラウドエンジニア 東京", "Kubernetes エンジニア 東京", "DevOpsエンジニア 東京", "ネットワークエンジニア 東京",
    "プラットフォームエンジニア 東京", "AWS エンジニア 東京", "インフラエンジニア Kubernetes", "サーバーエンジニア 東京",
    "Cloud engineer Japan English speaking", "Infrastructure engineer Japan remote", "Kubernetes SRE Japan English",
    "Terraform engineer Tokyo", "GCP engineer Tokyo", "OpenStack engineer Japan", "5G core network engineer Tokyo",
]


def fetch_jsearch(key: str, queries=JSEARCH_QUERIES, pages: int = 1) -> list[dict]:
    """Real postings aggregated from Google for Jobs (Indeed, LinkedIn, agencies, company sites). Needs RAPIDAPI_KEY.
    JSearch v5: endpoint /search-v2, results under data.jobs. Pulled in both Japanese and English."""
    out = []

    def one(args):
        q, lang = args
        r = requests.get("https://jsearch.p.rapidapi.com/search-v2",
                         params={"query": q, "page": "1", "num_pages": str(pages), "country": "jp", "language": lang, "date_posted": "month"},
                         headers={"X-RapidAPI-Key": key, "X-RapidAPI-Host": "jsearch.p.rapidapi.com"}, timeout=40)
        if r.status_code != 200:
            print("  ! jsearch", q, lang, r.status_code, r.text[:120], file=sys.stderr)
            return []
        data = r.json().get("data") or {}
        items = data.get("jobs", []) if isinstance(data, dict) else data
        res = []
        for j in items:
            loc = ", ".join(x for x in (j.get("job_city") or "", j.get("job_state") or "", j.get("job_country") or "") if x)
            res.append({"source": "jsearch", "board": (j.get("job_publisher") or "web").lower(), "title": j.get("job_title", ""),
                        "company": j.get("employer_name", ""), "location": loc or "Japan", "lang": lang,
                        "url": j.get("job_apply_link", ""), "description": j.get("job_description", ""),
                        "updated": j.get("job_posted_at_datetime_utc", "")})
        return res

    with ThreadPoolExecutor(4) as ex:
        for res in ex.map(one, [(q, lang) for q in queries for lang in ("ja", "en")]):
            out.extend(res)
    return out


def fetch_all() -> list[dict]:
    import os
    from dotenv import load_dotenv
    load_dotenv(".env")
    jobs = []
    with ThreadPoolExecutor(16) as ex:
        futs = {ex.submit(fetch_greenhouse, t): ("gh", t) for t in GREENHOUSE}
        futs.update({ex.submit(fetch_lever, c): ("lever", c) for c in LEVER})
        futs.update({ex.submit(fetch_workable, c): ("workable", c) for c in WORKABLE})
        futs.update({ex.submit(fetch_ashby, c): ("ashby", c) for c in ASHBY})
        futs.update({ex.submit(fetch_smartrecruiters, c): ("smartrecruiters", c) for c in SMARTRECRUITERS})
        futs.update({ex.submit(fetch_workday, *w): ("workday", w[0] + "/" + w[2]) for w in WORKDAY})
        if os.environ.get("RAPIDAPI_KEY"):
            futs[ex.submit(fetch_jsearch, os.environ["RAPIDAPI_KEY"])] = ("jsearch", "*")
        else:
            print("  (no RAPIDAPI_KEY in .env - skipping JSearch)")
        for f in as_completed(futs):
            try:
                jobs.extend(f.result())
            except Exception as e:  # noqa: BLE001
                print("  !", futs[f], type(e).__name__, file=sys.stderr)
    return jobs


EXCLUDE_RE = re.compile(r"intern|新卒|卒対象|sales|account executive|recruit|marketing|designer|product manager|"
                        r"customer success|business development|director|\bvp\b|head of", re.I)


def japan_engineering(jobs: list[dict]) -> list[dict]:
    seen, out = set(), []
    for j in jobs:
        if not JP_RE.search(j["location"]) or not TITLE_RE.search(j["title"]) or EXCLUDE_RE.search(j["title"]) \
                or len(j["description"]) < 300:
            continue
        key = (j["company"].lower(), re.sub(r"\W+", " ", j["title"].lower()).strip())
        if key in seen:
            continue
        seen.add(key)
        out.append(j)
    return out


COMPANY_NAMES = {
    "transferwise": "Wise", "wise": "Wise", "woven-by-toyota": "Woven by Toyota", "wovenbytoyota": "Woven by Toyota",
    "woven": "Woven by Toyota", "paypay": "PayPay", "smartnews": "SmartNews", "lycorp": "LY Corporation",
    "grafanalabs": "Grafana Labs", "cockroachlabs": "Cockroach Labs", "paloaltonetworks": "Palo Alto Networks",
    "purestorage": "Pure Storage", "preferrednetworks": "Preferred Networks", "treasuredata": "Treasure Data",
    "moneyforward": "Money Forward", "rapyutarobotics": "Rapyuta Robotics", "tier4": "TIER IV", "newrelic": "New Relic",
    "digitalocean": "DigitalOcean", "pingcap": "PingCAP", "scylladb": "ScyllaDB", "mongodb": "MongoDB", "gitlab": "GitLab",
    "github": "GitHub", "hashicorp": "HashiCorp", "pagerduty": "PagerDuty", "crowdstrike": "CrowdStrike",
    "doordash": "DoorDash", "bitflyer": "bitFlyer", "weightsandbiases": "Weights & Biases", "huggingface": "Hugging Face",
    "scaleai": "Scale AI", "openai": "OpenAI", "sumologic": "Sumo Logic", "aiand": "ai&", "siei": "Sony Interactive Entertainment",
    "coupanginternal": "Coupang", "mujininc": "Mujin", "ispace-inc": "ispace", "matchgroup": "Match Group", "limitbreak": "Limit Break",
    "extremenetworks": "Extreme Networks", "sierra-jp": "Sierra", "bjakcareer": "Bjak", "neuralconcept": "Neural Concept",
    "appliedintuition": "Applied Intuition", "boxinc": "Box", "andurilindustries": "Anduril", "paypaycard": "PayPay Card",
    "sambanovasystems": "SambaNova", "queracomputinginc": "QuEra", "hyphenconnect": "Hyphen Connect", "xai": "xAI",
    "deepmind": "Google DeepMind", "rakuten": "Rakuten", "dxctechnology": "DXC Technology", "renesaselectronics": "Renesas",
    "hitachisolutions": "Hitachi Solutions", "necsws": "NEC Software Solutions", "aristanetworks": "Arista Networks",
    "nagarro1": "Nagarro", "ifs1": "IFS", "ai-robot-association": "AI Robot Association", "rapyuta-robotics": "Rapyuta Robotics",
    "sakana-ai": "Sakana AI", "polymer-capital-japan": "Polymer Capital", "stack-infrastructure-apac-pte-ltd": "STACK Infrastructure",
    "twelve-labs": "Twelve Labs", "liquid-ai": "Liquid AI", "carnot-ai": "Carnot AI", "clickhouse": "ClickHouse",
    "verygoodsecurity": "Very Good Security", "route06": "ROUTE06", "lazarusenterprises": "Lazarus", "gatikaiinc": "Gatik",
    "keywordsstudios": "Keywords Studios", "applusidiada1": "Applus IDIADA", "boschgroup": "Bosch", "lingonetwork": "Lingo",
    "systemcanadatechnologies": "System Canada Technologies", "servicenow": "ServiceNow", "nextdc": "NEXTDC",
}


def pretty_company(board: str) -> str:
    key = board.split("/")[0].lower()
    return COMPANY_NAMES.get(key, key.capitalize())


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    cmd = sys.argv[1] if len(sys.argv) > 1 else "probe"
    t = time.perf_counter()
    raw = fetch_all()
    jp = japan_engineering(raw)
    print(f"fetched {len(raw)} postings from {len({j['board'] for j in raw})} boards in {time.perf_counter()-t:.0f}s; "
          f"{len(jp)} Japan engineering roles")
    from collections import Counter
    print(Counter(j["board"] for j in jp).most_common())
    if cmd == "probe":
        for j in jp[:40]:
            print(f"  - [{j['board']}] {j['title']}  @ {j['location']}")
        sys.exit()
    for j in jp:
        j["company"] = pretty_company(j["board"])
    json.dump(jp, open("demo/real_jobs_raw.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("saved demo/real_jobs_raw.json")
    if cmd == "extract":
        import llm
        t = time.perf_counter()
        done = []
        with ThreadPoolExecutor(8) as ex:
            futs = {ex.submit(llm.extract_job_requirements, j["title"], j["description"]): j for j in jp}
            for f in as_completed(futs):
                j = futs[f]
                try:
                    j["requires"] = f.result()
                    if len(j["requires"]) >= 3:
                        done.append(j)
                except Exception as e:  # noqa: BLE001
                    print("  ! extract failed:", j["title"], type(e).__name__, str(e)[:80])
        print(f"extracted requirements for {len(done)} jobs in {time.perf_counter()-t:.0f}s")
        json.dump(done, open("demo/real_jobs.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("saved demo/real_jobs.json")
