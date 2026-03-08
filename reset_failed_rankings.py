#!/usr/bin/env python3
"""Reset papers that failed ranking so they can be re-ranked."""

from dotenv import load_dotenv
load_dotenv()

from src.database import PaperDatabase

db = PaperDatabase()
with db._get_conn() as conn:
    # Reset rankings and digest flag so they get re-ranked and re-digested
    cur = conn.execute(
        "UPDATE papers SET relevance_score=NULL, summary=NULL, ranking_rationale=NULL, last_digest_date=NULL "
        "WHERE summary='[Error during ranking]'"
    )
    print(f"Reset {cur.rowcount} papers")
