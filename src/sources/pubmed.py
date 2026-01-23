"""
PubMed E-utilities client for searching and fetching paper metadata.

NCBI E-utilities documentation: https://www.ncbi.nlm.nih.gov/books/NBK25500/
"""

import json
import os
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import quote_plus

import requests


@dataclass
class Paper:
    """A paper retrieved from PubMed or bioRxiv."""
    id: str  # PMID or DOI
    source: str  # 'pubmed' or 'biorxiv'
    title: str
    authors: list[str]
    journal: str
    pub_date: str
    abstract: str
    url: str
    full_text_url: Optional[str] = None
    is_open_access: bool = False
    doi: Optional[str] = None

    # These will be filled in by the ranker
    summary: Optional[str] = None
    relevance_score: Optional[float] = None
    ranking_rationale: Optional[str] = None
    matched_projects: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "source": self.source,
            "title": self.title,
            "authors": self.authors,
            "journal": self.journal,
            "pub_date": self.pub_date,
            "abstract": self.abstract,
            "url": self.url,
            "full_text_url": self.full_text_url,
            "is_open_access": self.is_open_access,
            "doi": self.doi,
            "summary": self.summary,
            "relevance_score": self.relevance_score,
            "ranking_rationale": self.ranking_rationale,
            "matched_projects": self.matched_projects,
        }


class PubMedClient:
    """Client for searching PubMed using NCBI E-utilities."""

    BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    PUBMED_URL = "https://pubmed.ncbi.nlm.nih.gov"

    def __init__(self, api_key: Optional[str] = None, email: Optional[str] = None):
        """
        Initialize the PubMed client.

        Args:
            api_key: NCBI API key (optional but recommended for higher rate limits).
                     Get one at https://www.ncbi.nlm.nih.gov/account/settings/
            email: Email address for NCBI to contact if there are problems.
        """
        self.api_key = api_key or os.getenv("NCBI_API_KEY")
        self.email = email or os.getenv("NCBI_EMAIL")
        self.session = requests.Session()

        # Rate limiting: 3 requests/sec without API key, 10/sec with key
        # Being conservative to avoid 429s
        self._last_request_time = 0
        self._min_interval = 0.15 if self.api_key else 0.5

    def _rate_limit(self):
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request_time = time.time()

    def _request_with_retry(
        self, url: str, params: dict, max_retries: int = 3
    ) -> requests.Response:
        """Make a request with exponential backoff retry on 429 errors."""
        for attempt in range(max_retries):
            self._rate_limit()
            response = self.session.get(url, params=params)

            if response.status_code == 429:
                wait_time = (2 ** attempt) + 1  # 2, 3, 5 seconds
                print(f"    Rate limited, waiting {wait_time}s...")
                time.sleep(wait_time)
                continue

            response.raise_for_status()
            return response

        # Final attempt
        self._rate_limit()
        response = self.session.get(url, params=params)
        response.raise_for_status()
        return response

    def _build_params(self, **kwargs) -> dict:
        """Build request parameters with API key and email."""
        params = dict(kwargs)
        if self.api_key:
            params["api_key"] = self.api_key
        if self.email:
            params["email"] = self.email
        return params

    def search(
        self,
        query: str,
        max_results: int = 100,
        days_back: int = 7,
    ) -> list[str]:
        """
        Search PubMed and return a list of PMIDs.

        Args:
            query: Search query (uses PubMed query syntax).
            max_results: Maximum number of results to return.
            days_back: Only return papers from the last N days.

        Returns:
            List of PMIDs matching the query.
        """
        # Build date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        date_range = f"{start_date:%Y/%m/%d}:{end_date:%Y/%m/%d}[EDAT]"

        # Combine query with date filter
        full_query = f"({query}) AND {date_range}"

        params = self._build_params(
            db="pubmed",
            term=full_query,
            retmax=max_results,
            retmode="json",
            sort="relevance",
        )

        response = self._request_with_retry(f"{self.BASE_URL}/esearch.fcgi", params)

        data = response.json()
        result = data.get("esearchresult", {})

        if "ERROR" in result:
            raise ValueError(f"PubMed search error: {result['ERROR']}")

        pmids = result.get("idlist", [])
        count = int(result.get("count", 0))

        if count > max_results:
            print(f"  Note: {count} total results, returning first {max_results}")

        return pmids

    def fetch_papers(self, pmids: list[str]) -> list[Paper]:
        """
        Fetch full paper metadata for a list of PMIDs.

        Args:
            pmids: List of PubMed IDs to fetch.

        Returns:
            List of Paper objects with full metadata.
        """
        if not pmids:
            return []

        # Fetch in batches of 200 (NCBI limit)
        all_papers = []
        batch_size = 200

        for i in range(0, len(pmids), batch_size):
            batch = pmids[i : i + batch_size]
            papers = self._fetch_batch(batch)
            all_papers.extend(papers)

        return all_papers

    def _fetch_batch(self, pmids: list[str]) -> list[Paper]:
        """Fetch metadata for a batch of PMIDs."""
        params = self._build_params(
            db="pubmed",
            id=",".join(pmids),
            rettype="xml",
            retmode="xml",
        )

        response = self._request_with_retry(f"{self.BASE_URL}/efetch.fcgi", params)
        return self._parse_xml(response.text)

    def _parse_xml(self, xml_text: str) -> list[Paper]:
        """Parse PubMed XML response into Paper objects."""
        papers = []

        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            print(f"XML parse error: {e}")
            return papers

        for article in root.findall(".//PubmedArticle"):
            try:
                paper = self._parse_article(article)
                if paper:
                    papers.append(paper)
            except Exception as e:
                pmid = article.findtext(".//PMID", "unknown")
                print(f"Error parsing PMID {pmid}: {e}")

        return papers

    def _parse_article(self, article: ET.Element) -> Optional[Paper]:
        """Parse a single PubmedArticle element into a Paper object."""
        medline = article.find("MedlineCitation")
        if medline is None:
            return None

        pmid = medline.findtext("PMID", "")
        if not pmid:
            return None

        article_elem = medline.find("Article")
        if article_elem is None:
            return None

        # Title
        title = article_elem.findtext("ArticleTitle", "No title")

        # Authors
        authors = []
        author_list = article_elem.find("AuthorList")
        if author_list is not None:
            for author in author_list.findall("Author"):
                last_name = author.findtext("LastName", "")
                initials = author.findtext("Initials", "")
                if last_name:
                    authors.append(f"{last_name} {initials}".strip())

        # Journal
        journal_elem = article_elem.find("Journal")
        journal = ""
        if journal_elem is not None:
            journal = journal_elem.findtext("Title", "")
            if not journal:
                journal = journal_elem.findtext("ISOAbbreviation", "")

        # Publication date
        pub_date = self._extract_pub_date(article_elem)

        # Abstract
        abstract_elem = article_elem.find("Abstract")
        abstract = ""
        if abstract_elem is not None:
            abstract_parts = []
            for text in abstract_elem.findall("AbstractText"):
                label = text.get("Label", "")
                content = "".join(text.itertext())
                if label:
                    abstract_parts.append(f"{label}: {content}")
                else:
                    abstract_parts.append(content)
            abstract = " ".join(abstract_parts)

        # DOI
        doi = None
        article_id_list = article.find(".//ArticleIdList")
        if article_id_list is not None:
            for aid in article_id_list.findall("ArticleId"):
                if aid.get("IdType") == "doi":
                    doi = aid.text
                    break

        # Check for PMC (free full text)
        pmc_id = None
        if article_id_list is not None:
            for aid in article_id_list.findall("ArticleId"):
                if aid.get("IdType") == "pmc":
                    pmc_id = aid.text
                    break

        is_open_access = pmc_id is not None
        full_text_url = None
        if pmc_id:
            full_text_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmc_id}/"

        return Paper(
            id=pmid,
            source="pubmed",
            title=title,
            authors=authors,
            journal=journal,
            pub_date=pub_date,
            abstract=abstract,
            url=f"{self.PUBMED_URL}/{pmid}/",
            full_text_url=full_text_url,
            is_open_access=is_open_access,
            doi=doi,
        )

    def _extract_pub_date(self, article: ET.Element) -> str:
        """Extract publication date from article element."""
        # Try ArticleDate first (electronic publication)
        article_date = article.find(".//ArticleDate")
        if article_date is not None:
            year = article_date.findtext("Year", "")
            month = article_date.findtext("Month", "01")
            day = article_date.findtext("Day", "01")
            if year:
                return f"{year}-{month.zfill(2)}-{day.zfill(2)}"

        # Fall back to Journal PubDate
        pub_date = article.find(".//Journal/JournalIssue/PubDate")
        if pub_date is not None:
            year = pub_date.findtext("Year", "")
            month = pub_date.findtext("Month", "01")
            day = pub_date.findtext("Day", "01")

            # Month might be text like "Jan"
            month_map = {
                "Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04",
                "May": "05", "Jun": "06", "Jul": "07", "Aug": "08",
                "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12",
            }
            if month in month_map:
                month = month_map[month]

            if year:
                return f"{year}-{month.zfill(2)}-{day.zfill(2)}"

        return "Unknown"

    def search_and_fetch(
        self,
        query: str,
        max_results: int = 100,
        days_back: int = 7,
    ) -> list[Paper]:
        """
        Search PubMed and fetch full metadata in one call.

        Args:
            query: Search query.
            max_results: Maximum number of results.
            days_back: Only return papers from the last N days.

        Returns:
            List of Paper objects with full metadata.
        """
        pmids = self.search(query, max_results=max_results, days_back=days_back)
        if not pmids:
            return []
        return self.fetch_papers(pmids)


if __name__ == "__main__":
    # Quick test
    client = PubMedClient()
    print("Searching for 'biliary atresia gut microbiome'...")
    papers = client.search_and_fetch(
        "biliary atresia gut microbiome",
        max_results=5,
        days_back=30,
    )
    print(f"Found {len(papers)} papers")
    for p in papers:
        print(f"\n- {p.title}")
        print(f"  Authors: {', '.join(p.authors[:3])}{'...' if len(p.authors) > 3 else ''}")
        print(f"  Journal: {p.journal}")
        print(f"  Date: {p.pub_date}")
        print(f"  URL: {p.url}")
