#!/usr/bin/env python3
"""Reset papers for re-ranking or re-digesting.

Usage:
    python reset_failed_rankings.py          # Reset failed rankings + digest flag
    python reset_failed_rankings.py --digest # Only clear digest flag on recent papers
"""

import argparse
from dotenv import load_dotenv
load_dotenv()

from src.database import PaperDatabase

parser = argparse.ArgumentParser()
parser.add_argument("--digest", action="store_true", help="Only clear last_digest_date on recent papers")
parser.add_argument("--days", type=int, default=7, help="Days lookback (default: 7)")
args = parser.parse_args()

db = PaperDatabase()
with db._get_conn() as conn:
    if args.digest:
        cur = conn.execute(
            "UPDATE papers SET last_digest_date=NULL "
            "WHERE last_digest_date IS NOT NULL "
            "AND first_seen_date >= date('now', '-' || ? || ' days')",
            (args.days,)
        )
        print(f"Cleared digest flag on {cur.rowcount} papers")
    else:
        cur = conn.execute(
            "UPDATE papers SET relevance_score=NULL, summary=NULL, "
            "ranking_rationale=NULL, last_digest_date=NULL "
            "WHERE summary='[Error during ranking]'"
        )
        print(f"Reset {cur.rowcount} failed papers")
        # Also clear digest flag on any recently ranked papers
        cur2 = conn.execute(
            "UPDATE papers SET last_digest_date=NULL "
            "WHERE last_digest_date IS NOT NULL "
            "AND first_seen_date >= date('now', '-' || ? || ' days')",
            (args.days,)
        )
        print(f"Cleared digest flag on {cur2.rowcount} papers")
