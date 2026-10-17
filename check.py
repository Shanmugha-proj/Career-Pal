"""Pre-demo health check: Neo4j Aura + ai& inference. Run: python check.py"""
import os
import time

from dotenv import load_dotenv

load_dotenv(".env")


def check_neo4j():
    from neo4j import GraphDatabase

    with GraphDatabase.driver(os.environ["NEO4J_URI"], auth=(os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"])) as d:
        d.verify_connectivity()
        db = os.environ.get("NEO4J_DATABASE")
        t = time.perf_counter()
        recs, _, _ = d.execute_query(
            "RETURN count{ (:Job) } AS jobs, count{ (:Skill) } AS skills", database_=db
        )
        ms = 1000 * (time.perf_counter() - t)
        print(f"[OK] Neo4j  {ms:.0f} ms | jobs={recs[0]['jobs']} skills={recs[0]['skills']}")


def check_aiand():
    from openai import OpenAI

    key = os.environ.get("AIAND_API_KEY", "")
    if not key:
        print("[!!] ai&    AIAND_API_KEY is empty in .env")
        return
    client = OpenAI(base_url=os.environ["AIAND_BASE_URL"], api_key=key)
    t = time.perf_counter()
    r = client.chat.completions.create(
        model=os.environ["AIAND_MODEL"],
        messages=[{"role": "user", "content": "Reply with exactly: pong"}],
        max_tokens=5,
    )
    ms = 1000 * (time.perf_counter() - t)
    print(f"[OK] ai&    {ms:.0f} ms | {os.environ['AIAND_MODEL']} -> {r.choices[0].message.content!r}")


if __name__ == "__main__":
    for fn in (check_neo4j, check_aiand):
        try:
            fn()
        except Exception as e:  # noqa: BLE001 - this is a diagnostic script
            print(f"[!!] {fn.__name__}: {type(e).__name__}: {e}")
