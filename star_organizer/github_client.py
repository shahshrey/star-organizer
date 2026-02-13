from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List

import requests
import structlog

from star_organizer.models import (
    GITHUB_API_TIMEOUT_SECONDS,
    GITHUB_TOKEN,
    PARALLEL_METADATA_WORKERS,
    README_LINES_TO_FETCH,
    RepoMetadata,
)

LOGGER = structlog.get_logger()


def _auth_headers(accept: str) -> Dict[str, str]:
    return {
        "Accept": accept,
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def fetch_starred_repos(limit: int = 0) -> List[Dict[str, Any]]:
    if not GITHUB_TOKEN:
        LOGGER.error("missing_github_token")
        return []

    all_repos: List[Dict[str, Any]] = []
    page = 1
    per_page = 100
    headers = _auth_headers("application/vnd.github+json")

    while True:
        LOGGER.info("fetching_page", page=page)
        try:
            response = requests.get(
                "https://api.github.com/user/starred",
                headers=headers,
                params={"per_page": per_page, "page": page},
                timeout=30,
            )
            if response.status_code != 200:
                LOGGER.error("fetch_failed", page=page, status=response.status_code)
                break

            repos = response.json()
            if not repos:
                break

            LOGGER.info("fetched_repos", page=page, count=len(repos))
            all_repos.extend(repos)

            if limit and len(all_repos) >= limit:
                all_repos = all_repos[:limit]
                LOGGER.info("test_limit_reached", limit=limit)
                break

            if len(repos) < per_page:
                break

            page += 1
        except Exception as e:
            LOGGER.error("request_failed", page=page, error=str(e))
            break

    return all_repos


def _fetch_readme(full_name: str) -> str:
    if not full_name or not GITHUB_TOKEN:
        return ""
    try:
        resp = requests.get(
            f"https://api.github.com/repos/{full_name}/readme",
            headers=_auth_headers("application/vnd.github.raw"),
            timeout=GITHUB_API_TIMEOUT_SECONDS,
        )
        if resp.status_code != 200:
            return ""
        lines = resp.text.split("\n")
        return "\n".join([l for l in lines if l.strip()][:README_LINES_TO_FETCH])
    except requests.Timeout:
        return ""
    except Exception:
        return ""


def _build_metadata(repo: Dict[str, Any], readme: str) -> RepoMetadata:
    return {
        "url": repo.get("html_url", ""),
        "name": repo.get("name", ""),
        "full_name": repo.get("full_name", ""),
        "description": repo.get("description", "") or "",
        "topics": repo.get("topics", []),
        "readme": readme,
    }


def extract_repos_metadata(repos: List[Dict[str, Any]]) -> List[RepoMetadata]:
    if not repos:
        return []

    LOGGER.info("starting_metadata_extraction", total=len(repos), workers=PARALLEL_METADATA_WORKERS)
    results: List[RepoMetadata] = [_build_metadata(r, "") for r in repos]
    completed = 0

    with ThreadPoolExecutor(max_workers=PARALLEL_METADATA_WORKERS) as executor:
        future_to_idx = {
            executor.submit(_fetch_readme, repo.get("full_name", "")): idx
            for idx, repo in enumerate(repos)
        }
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                readme = future.result()
                results[idx] = _build_metadata(repos[idx], readme)
            except Exception as e:
                LOGGER.error("readme_fetch_failed", repo=repos[idx].get("full_name", ""), error=str(e))

            completed += 1
            if completed % 50 == 0:
                LOGGER.info("metadata_progress", completed=completed, total=len(repos))

    LOGGER.info("metadata_extraction_complete", total=len(results))
    return results
