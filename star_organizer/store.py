import json
import os
from datetime import datetime, timezone
from typing import Set

import structlog

from star_organizer.models import OrganizedStarLists

LOGGER = structlog.get_logger()


def load_organized_stars(path: str) -> OrganizedStarLists:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data: OrganizedStarLists = json.load(f)
        for list_data in data.values():
            if "repos" not in list_data:
                list_data["repos"] = []
            if "description" not in list_data:
                list_data["description"] = ""
        return data
    except Exception as e:
        LOGGER.error("load_organized_stars_failed", file=path, error=str(e))
        return {}


def save_organized_stars(path: str, data: OrganizedStarLists) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        LOGGER.error("save_organized_stars_failed", file=path, error=str(e))


def canonicalize_repo_url(url: str) -> str:
    import re

    s = (url or "").strip()
    if not s:
        return ""
    s = s.replace(".git", "")
    m = re.search(r"github\.com[:/]+([^/]+)/([^/?#]+)", s, re.IGNORECASE)
    if not m:
        return s
    return f"https://github.com/{m.group(1)}/{m.group(2)}"


def load_sync_state(path: str) -> Set[str]:
    if not path or not os.path.exists(path):
        return set()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
        urls = data.get("synced_repo_urls", [])
        if not isinstance(urls, list):
            return set()
        return {canonicalize_repo_url(u) for u in urls if isinstance(u, str) and u.strip()}
    except Exception as e:
        LOGGER.warning("sync_state_load_failed", file=path, error=str(e))
        return set()


def save_sync_state(path: str, synced_urls: Set[str]) -> None:
    if not path:
        return
    payload = {
        "version": 1,
        "last_updated_at": datetime.now(timezone.utc).isoformat(),
        "synced_repo_urls": sorted(synced_urls),
    }
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
    except Exception as e:
        LOGGER.error("sync_state_save_failed", file=path, error=str(e))


def extract_all_repo_urls(organized: OrganizedStarLists) -> Set[str]:
    urls: Set[str] = set()
    for list_data in organized.values():
        for repo in list_data.get("repos", []):
            if isinstance(repo, dict):
                urls.add(repo.get("url", ""))
            else:
                urls.add(repo)
    return urls
