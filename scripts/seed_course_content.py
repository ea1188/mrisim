#!/usr/bin/env python3
"""Load the EXCLUSIVE premium course content into Supabase `course_content`.

Run by the project owner with the **service_role** key (which bypasses RLS) — the
content is deliberately not in the public site, so only this trusted path writes it.
Idempotent: it clears the course's rows and re-inserts from data/course_content.json.

    SUPABASE_URL=https://<ref>.supabase.co \
    SUPABASE_SERVICE_ROLE=<service_role key> \
    python scripts/seed_course_content.py

Never commit the service_role key. See docs/COURSE.md.
"""
import json
import os
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(HERE, "data", "course_content.json")


def _req(method: str, url: str, key: str, body=None):
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def main() -> int:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE", "")
    if not url or not key:
        print("Set SUPABASE_URL and SUPABASE_SERVICE_ROLE (service_role key).", file=sys.stderr)
        return 2

    data = json.load(open(SRC))
    course = data["course"]
    rows = [
        {"course": course, "topic": it["topic"], "kind": it["kind"],
         "ord": int(it.get("ord", 0)), "body": it["body"]}
        for it in data["items"]
    ]
    print(f"Seeding {len(rows)} items for course '{course}' → {url}")

    # 1) Clear this course's rows (idempotent re-seed).
    st, msg = _req("DELETE", f"{url}/rest/v1/course_content?course=eq.{course}", key)
    if st not in (200, 204):
        print(f"delete failed: HTTP {st} {msg}", file=sys.stderr)
        return 1

    # 2) Insert the current content (single bulk insert; uniform keys).
    st, msg = _req("POST", f"{url}/rest/v1/course_content", key, rows)
    if st not in (200, 201, 204):
        print(f"insert failed: HTTP {st} {msg}", file=sys.stderr)
        return 1

    print("Done. Entitled users can now read the premium content.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
