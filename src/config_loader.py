"""
Config loader for literature monitoring tool.
Loads and validates YAML configuration files.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class Project:
    """An active research project with associated keywords."""
    name: str
    keywords: list[str]


@dataclass
class JournalTier:
    """A tier of journals with an associated weight multiplier."""
    weight: float
    journals: list[str]


@dataclass
class Config:
    """Main configuration object for the literature monitor."""
    search_queries: list[str]
    watched_authors: list[str]
    active_projects: list[Project]
    journal_weights: dict[str, JournalTier]

    # Optional settings with defaults
    email_to: Optional[str] = None
    email_from: Optional[str] = None
    max_results_per_query: int = 100
    days_lookback: int = 7
    min_relevance_score: float = 0.3

    def get_journal_weight(self, journal_name: str) -> float:
        """Get the weight multiplier for a journal (default 1.0 if not configured)."""
        for tier in self.journal_weights.values():
            if journal_name in tier.journals:
                return tier.weight
        return 1.0

    def get_all_keywords(self) -> set[str]:
        """Get all keywords across all active projects."""
        keywords = set()
        for project in self.active_projects:
            keywords.update(project.keywords)
        return keywords

    def match_projects(self, text: str) -> list[str]:
        """Find which projects match the given text (title + abstract)."""
        text_lower = text.lower()
        matched = []
        for project in self.active_projects:
            for keyword in project.keywords:
                if keyword.lower() in text_lower:
                    matched.append(project.name)
                    break
        return matched


def load_config(config_path: str | Path | None = None) -> Config:
    """
    Load configuration from a YAML file.

    Args:
        config_path: Path to config.yaml. Defaults to config/config.yaml
                     relative to the project root.

    Returns:
        Config object with all settings.

    Raises:
        FileNotFoundError: If config file doesn't exist.
        ValueError: If config is invalid.
    """
    if config_path is None:
        # Default to config/config.yaml relative to this file's parent's parent
        project_root = Path(__file__).parent.parent
        config_path = project_root / "config" / "config.yaml"
    else:
        config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, "r") as f:
        raw = yaml.safe_load(f)

    return parse_config(raw)


def parse_config(raw: dict) -> Config:
    """Parse raw YAML dict into a Config object."""
    if not raw:
        raise ValueError("Config file is empty")

    # Required fields
    search_queries = raw.get("search_queries", [])
    if not search_queries:
        raise ValueError("Config must have at least one search query")

    watched_authors = raw.get("watched_authors", [])

    # Parse active projects
    active_projects = []
    for proj in raw.get("active_projects", []):
        if isinstance(proj, dict) and "name" in proj:
            active_projects.append(Project(
                name=proj["name"],
                keywords=proj.get("keywords", [])
            ))

    # Parse journal weights
    journal_weights = {}
    for tier_name, tier_data in raw.get("journal_weights", {}).items():
        if isinstance(tier_data, dict):
            journal_weights[tier_name] = JournalTier(
                weight=float(tier_data.get("weight", 1.0)),
                journals=tier_data.get("journals", [])
            )

    # Optional settings
    settings = raw.get("settings", {})

    return Config(
        search_queries=search_queries,
        watched_authors=watched_authors,
        active_projects=active_projects,
        journal_weights=journal_weights,
        email_to=settings.get("email_to") or os.getenv("EMAIL_TO"),
        email_from=settings.get("email_from") or os.getenv("EMAIL_FROM"),
        max_results_per_query=settings.get("max_results_per_query", 100),
        days_lookback=settings.get("days_lookback", 7),
        min_relevance_score=settings.get("min_relevance_score", 0.3),
    )


if __name__ == "__main__":
    # Quick test
    config = load_config()
    print(f"Loaded {len(config.search_queries)} search queries")
    print(f"Watching {len(config.watched_authors)} authors")
    print(f"Tracking {len(config.active_projects)} projects")
