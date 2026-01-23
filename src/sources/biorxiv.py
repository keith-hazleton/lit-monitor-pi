"""
bioRxiv/medRxiv API client for searching and fetching preprint metadata.

bioRxiv API documentation: https://api.biorxiv.org/

Note: bioRxiv doesn't have a search API like PubMed. Instead, we fetch
recent papers and filter locally based on keywords.
"""

import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import requests

from .pubmed import Paper


class BioRxivClient:
    """Client for fetching preprints from bioRxiv and medRxiv."""

    BASE_URL = "https://api.biorxiv.org"

    def __init__(self, include_medrxiv: bool = True):
        """
        Initialize the bioRxiv client.

        Args:
            include_medrxiv: Whether to also search medRxiv (default True).
        """
        self.include_medrxiv = include_medrxiv
        self.session = requests.Session()
        self._last_request_time = 0
        self._min_interval = 0.5  # Be conservative with rate limiting

    def _rate_limit(self):
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request_time = time.time()

    def _fetch_papers_from_server(
        self,
        server: str,
        start_date: str,
        end_date: str,
        max_results: int = 500,
    ) -> list[dict]:
        """
        Fetch papers from a specific server (biorxiv or medrxiv).

        Args:
            server: 'biorxiv' or 'medrxiv'
            start_date: Start date in YYYY-MM-DD format.
            end_date: End date in YYYY-MM-DD format.
            max_results: Maximum number of results to fetch.

        Returns:
            List of paper dictionaries from the API.
        """
        all_papers = []
        cursor = 0
        page_size = 100  # API returns up to 100 per page

        while len(all_papers) < max_results:
            self._rate_limit()

            url = f"{self.BASE_URL}/details/{server}/{start_date}/{end_date}/{cursor}"

            try:
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                data = response.json()
            except requests.RequestException as e:
                print(f"    Error fetching from {server}: {e}")
                break

            papers = data.get("collection", [])
            if not papers:
                break

            all_papers.extend(papers)

            # Check if there are more pages
            messages = data.get("messages", [])
            total = 0
            for msg in messages:
                if "total" in msg:
                    total = int(msg.get("total", 0))
                    break

            cursor += page_size
            if cursor >= total:
                break

        return all_papers[:max_results]

    def _matches_query(self, paper: dict, query: str) -> bool:
        """
        Check if a paper matches a search query.

        Uses simple keyword matching on title and abstract.
        """
        # Normalize query - split into terms
        query_lower = query.lower()

        # Handle quoted phrases
        phrases = re.findall(r'"([^"]+)"', query_lower)
        # Remove quoted phrases and get remaining terms
        remaining = re.sub(r'"[^"]+"', '', query_lower)
        terms = [t.strip() for t in remaining.split() if t.strip()]

        # Combine title and abstract for searching
        title = (paper.get("title") or "").lower()
        abstract = (paper.get("abstract") or "").lower()
        text = f"{title} {abstract}"

        # Check phrases (must match exactly)
        for phrase in phrases:
            if phrase not in text:
                return False

        # Check individual terms (all must be present)
        for term in terms:
            if term not in text:
                return False

        return True

    def _convert_to_paper(self, data: dict, server: str) -> Paper:
        """Convert bioRxiv API response to Paper object."""
        # Parse authors
        authors_str = data.get("authors", "")
        if authors_str:
            # bioRxiv format: "Last, First; Last, First; ..."
            authors = []
            for author in authors_str.split(";"):
                author = author.strip()
                if author:
                    # Convert "Last, First" to "Last F" format
                    parts = author.split(",")
                    if len(parts) >= 2:
                        last = parts[0].strip()
                        first = parts[1].strip()
                        initials = "".join(n[0] for n in first.split() if n)
                        authors.append(f"{last} {initials}")
                    else:
                        authors.append(author)
        else:
            authors = []

        # Get DOI
        doi = data.get("doi", "")

        # Build URLs
        url = f"https://www.{server}.org/content/{doi}"
        pdf_url = f"{url}.full.pdf"

        # Parse date
        pub_date = data.get("date", "")

        return Paper(
            id=doi,  # Use DOI as ID
            source=server,
            title=data.get("title", "No title"),
            authors=authors,
            journal=f"{server} (preprint)",
            pub_date=pub_date,
            abstract=data.get("abstract", ""),
            url=url,
            full_text_url=pdf_url,  # bioRxiv preprints are always open access
            is_open_access=True,
            doi=doi,
        )

    def fetch_recent(
        self,
        days_back: int = 7,
        max_results: int = 500,
    ) -> list[Paper]:
        """
        Fetch recent papers from bioRxiv (and optionally medRxiv).

        Args:
            days_back: Number of days to look back.
            max_results: Maximum results per server.

        Returns:
            List of Paper objects.
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)

        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")

        all_papers = []

        # Fetch from bioRxiv
        print(f"    Fetching from bioRxiv ({start_str} to {end_str})...")
        biorxiv_data = self._fetch_papers_from_server(
            "biorxiv", start_str, end_str, max_results
        )
        for data in biorxiv_data:
            all_papers.append(self._convert_to_paper(data, "biorxiv"))
        print(f"    Found {len(biorxiv_data)} papers from bioRxiv")

        # Fetch from medRxiv if enabled
        if self.include_medrxiv:
            print(f"    Fetching from medRxiv ({start_str} to {end_str})...")
            medrxiv_data = self._fetch_papers_from_server(
                "medrxiv", start_str, end_str, max_results
            )
            for data in medrxiv_data:
                all_papers.append(self._convert_to_paper(data, "medrxiv"))
            print(f"    Found {len(medrxiv_data)} papers from medRxiv")

        return all_papers

    def search_and_fetch(
        self,
        query: str,
        max_results: int = 100,
        days_back: int = 7,
    ) -> list[Paper]:
        """
        Search bioRxiv/medRxiv by fetching recent papers and filtering.

        Args:
            query: Search query (keywords to match in title/abstract).
            max_results: Maximum number of matching results to return.
            days_back: Only return papers from the last N days.

        Returns:
            List of Paper objects matching the query.
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)

        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")

        matching_papers = []

        # Search bioRxiv
        biorxiv_data = self._fetch_papers_from_server(
            "biorxiv", start_str, end_str, max_results=1000
        )
        for data in biorxiv_data:
            if self._matches_query(data, query):
                matching_papers.append(self._convert_to_paper(data, "biorxiv"))
                if len(matching_papers) >= max_results:
                    break

        # Search medRxiv if enabled and need more results
        if self.include_medrxiv and len(matching_papers) < max_results:
            medrxiv_data = self._fetch_papers_from_server(
                "medrxiv", start_str, end_str, max_results=1000
            )
            for data in medrxiv_data:
                if self._matches_query(data, query):
                    matching_papers.append(self._convert_to_paper(data, "medrxiv"))
                    if len(matching_papers) >= max_results:
                        break

        return matching_papers[:max_results]


if __name__ == "__main__":
    # Quick test
    client = BioRxivClient()
    print("Searching bioRxiv for 'liver microbiome'...")
    papers = client.search_and_fetch(
        "liver microbiome",
        max_results=5,
        days_back=30,
    )
    print(f"Found {len(papers)} papers")
    for p in papers:
        print(f"\n- {p.title}")
        print(f"  Authors: {', '.join(p.authors[:3])}{'...' if len(p.authors) > 3 else ''}")
        print(f"  Source: {p.source}")
        print(f"  Date: {p.pub_date}")
        print(f"  URL: {p.url}")
