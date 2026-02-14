from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Tuple

import requests
import structlog

from star_organizer.models import GITHUB_API_TIMEOUT_SECONDS, GITHUB_TOKEN, PARALLEL_METADATA_WORKERS

LOGGER = structlog.get_logger()

DEAD_CHECK_WORKERS = min(PARALLEL_METADATA_WORKERS, 10)


def _auth_headers() -> Dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _check_repo_alive(full_name: str) -> Tuple[str, int]:
    if not full_name or not GITHUB_TOKEN:
        return full_name, -1
    try:
        resp = requests.get(
            f"https://api.github.com/repos/{full_name}",
            headers=_auth_headers(),
            timeout=GITHUB_API_TIMEOUT_SECONDS,
            allow_redirects=True,
        )
        if resp.status_code == 403:
            remaining = resp.headers.get("X-RateLimit-Remaining", "")
            if remaining == "0":
                return full_name, 200
        return full_name, resp.status_code
    except requests.Timeout:
        return full_name, -2
    except Exception:
        return full_name, -1


def find_dead_repos(repos: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    if not repos:
        return [], {}

    dead: List[Dict[str, Any]] = []
    status_map: Dict[str, int] = {}
    name_to_repo = {r.get("full_name", ""): r for r in repos if r.get("full_name")}

    with ThreadPoolExecutor(max_workers=DEAD_CHECK_WORKERS) as executor:
        futures = {
            executor.submit(_check_repo_alive, name): name
            for name in name_to_repo
        }
        completed = 0
        for future in as_completed(futures):
            full_name, status = future.result()
            status_map[full_name] = status
            if status in (404, 403, 451, -1):
                repo = name_to_repo.get(full_name)
                if repo:
                    dead.append(repo)

            completed += 1
            if completed % 20 == 0:
                LOGGER.info("dead_check_progress", completed=completed, total=len(name_to_repo))

    dead.sort(key=lambda r: r.get("full_name", ""))
    return dead, status_map


def dead_status_label(code: int) -> str:
    labels = {
        404: "Deleted / Not Found",
        403: "Private / Forbidden",
        451: "DMCA Takedown",
        -1: "Network Error",
        -2: "Timeout",
    }
    return labels.get(code, f"HTTP {code}")
