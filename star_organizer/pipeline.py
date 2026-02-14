import os
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Set, Tuple

import structlog

from star_organizer.categorizer import categorize_repos, create_categories
from star_organizer.github_client import extract_repos_metadata, fetch_starred_repos
from star_organizer.github_sync import (
    add_repos_to_lists,
    delete_all_lists,
    fetch_repo_ids,
    format_list_name,
    parse_repo_url,
    resolve_list_ids,
)
from star_organizer.models import (
    GITHUB_TOKEN,
    MAX_GITHUB_LISTS,
    OPENAI_API_KEY,
    OUTPUT_FILE,
    RATE_LIMIT_ITEM,
    RATE_LIMIT_LIST,
    SYNC_STATE_FILE,
    OrganizedStarLists,
    RepoMetadata,
)
from star_organizer.rate_limiter import RateLimiter
from star_organizer.store import (
    canonicalize_repo_url,
    extract_all_repo_urls,
    load_organized_stars,
    load_sync_state,
    save_organized_stars,
    save_sync_state,
)

LOGGER = structlog.get_logger()


def validate_tokens(sync_only: bool = False) -> Tuple[bool, str]:
    if not GITHUB_TOKEN:
        return False, "GITHUB_TOKEN is not set"
    if not sync_only and not OPENAI_API_KEY:
        return False, "OPENAI_API_KEY is not set (required for categorization)"
    return True, ""


def create_backup(output_file: str) -> str:
    if not os.path.exists(output_file):
        return ""
    backup_path = f"{output_file}.backup.{int(time.time())}"
    with open(output_file, "r", encoding="utf-8") as src:
        with open(backup_path, "w", encoding="utf-8") as dst:
            dst.write(src.read())
    return backup_path


def phase_1_fetch_and_load(
    reset: bool,
    state_file: str,
    output_file: str,
    test_limit: int,
) -> Tuple[List[dict], OrganizedStarLists, Set[str]]:
    LOGGER.info("phase_1_fetch_and_load")

    with ThreadPoolExecutor(max_workers=2) as ex:
        repos_future = ex.submit(fetch_starred_repos, test_limit)

        def load_state():
            organized = {} if reset else load_organized_stars(output_file)
            synced = set() if reset else load_sync_state(state_file)
            return organized, synced

        state_future = ex.submit(load_state)
        repos = repos_future.result()
        organized, already_synced = state_future.result()

    LOGGER.info(
        "phase_1_complete",
        starred=len(repos),
        existing_categories=len(organized),
        already_synced=len(already_synced),
    )
    return repos, organized, already_synced


def phase_2_metadata(
    repos: List[dict],
    organized: OrganizedStarLists,
    reset: bool,
) -> Tuple[List[RepoMetadata], List[RepoMetadata]]:
    LOGGER.info("phase_2_metadata_extraction")

    already_categorized = extract_all_repo_urls(organized) if not reset else set()
    all_metadata = extract_repos_metadata(repos)

    new_metadata = [
        m for m in all_metadata
        if m["url"] not in already_categorized
    ]

    LOGGER.info(
        "phase_2_complete",
        total_metadata=len(all_metadata),
        new_repos=len(new_metadata),
        skipped=len(all_metadata) - len(new_metadata),
    )
    return all_metadata, new_metadata


def phase_3_categorize(
    all_metadata: List[RepoMetadata],
    new_metadata: List[RepoMetadata],
    organized: OrganizedStarLists,
    reset: bool,
    output_file: str,
) -> OrganizedStarLists:
    LOGGER.info("phase_3_categorization")

    need_categories = not organized or len(organized) > MAX_GITHUB_LISTS or reset
    repos_to_categorize = list(new_metadata)

    if need_categories:
        LOGGER.info("creating_new_categories", using_repos=len(all_metadata))
        categories = create_categories(all_metadata)

        old_repo_urls: set = set()
        if not reset:
            old_repo_urls = extract_all_repo_urls(organized)

        organized = {
            name: {"description": desc, "repos": []}
            for name, desc in categories.items()
        }
        save_organized_stars(output_file, organized)
        LOGGER.info("categories_saved", count=len(organized))

        if old_repo_urls:
            metadata_by_url = {m["url"]: m for m in all_metadata}
            new_urls = {m["url"] for m in new_metadata}
            old_metadata = [metadata_by_url[url] for url in old_repo_urls if url in metadata_by_url and url not in new_urls]
            repos_to_categorize = old_metadata + repos_to_categorize
            LOGGER.info("repos_queued_for_recategorization", old=len(old_metadata), new=len(new_metadata))

    if not repos_to_categorize:
        LOGGER.info("no_repos_to_categorize")
        return organized

    count = categorize_repos(repos_to_categorize, organized, save_organized_stars, output_file)
    LOGGER.info("phase_3_complete", categorized=count)
    return organized


def phase_4_sync(
    organized: OrganizedStarLists,
    already_synced: Set[str],
    reset: bool,
    state_file: str,
) -> Tuple[int, int, int]:
    LOGGER.info("phase_4_github_sync", reset=reset)

    list_limiter = RateLimiter(RATE_LIMIT_LIST)
    item_limiter = RateLimiter(RATE_LIMIT_ITEM)

    tasks: List[Tuple[str, str, str]] = []
    for cat_name, cat_data in organized.items():
        for repo in cat_data.get("repos", []):
            if not isinstance(repo, dict):
                continue
            url = canonicalize_repo_url(repo.get("url", ""))
            if not url:
                continue
            if not reset and url in already_synced:
                continue
            owner, name = parse_repo_url(url)
            if not owner or not name:
                continue
            tasks.append((cat_name, f"{owner}/{name}", url))

    if not tasks:
        LOGGER.info("nothing_to_sync")
        return 0, 0, 0

    repo_pairs = list({(t[1].split("/")[0], t[1].split("/")[1]) for t in tasks})
    LOGGER.info("sync_plan", repos_to_sync=len(tasks), unique_repos=len(repo_pairs))

    with ThreadPoolExecutor(max_workers=2) as ex:
        if reset:
            delete_future = ex.submit(delete_all_lists, list_limiter)
        else:
            delete_future = None

        repo_ids_future = ex.submit(fetch_repo_ids, repo_pairs, item_limiter)

        if delete_future:
            delete_future.result()
            LOGGER.info("barrier_delete_complete")

        repo_ids = repo_ids_future.result()

    LOGGER.info("repo_ids_resolved", found=len(repo_ids), total=len(repo_pairs))

    needed_categories = {t[0] for t in tasks}
    list_ids = resolve_list_ids(organized, list_limiter, needed_categories)
    LOGGER.info("lists_ready", count=len(list_ids))

    ops: List[Tuple[str, str, str, str]] = []
    full_name_to_url: Dict[str, str] = {}
    skipped = 0
    missing_lists: set = set()

    for cat_name, repo_full, repo_url in tasks:
        list_id = list_ids.get(cat_name, "")
        if not list_id:
            missing_lists.add(cat_name)
            continue
        owner, name = repo_full.split("/", 1)
        rid = repo_ids.get((owner, name), "")
        if not rid:
            skipped += 1
            continue
        ops.append((cat_name, rid, repo_full, list_id))
        full_name_to_url[repo_full] = repo_url

    if missing_lists:
        LOGGER.warning("categories_skipped_no_list_id", categories=sorted(missing_lists), count=len(missing_lists))

    if skipped:
        LOGGER.info("repos_skipped_no_id", count=skipped)

    total, success, stats, error_types, ok_repos = add_repos_to_lists(ops, item_limiter)
    rate = (success / total * 100) if total else 0.0

    LOGGER.info(
        "sync_complete",
        added=success,
        failed=total - success,
        skipped=skipped,
        success_rate=f"{rate:.1f}%",
    )

    if stats:
        for cat, count in sorted(stats.items(), key=lambda x: x[1], reverse=True):
            LOGGER.info("category_sync_stats", category=format_list_name(cat), count=count)

    if error_types:
        for etype, count in sorted(error_types.items(), key=lambda x: x[1], reverse=True):
            LOGGER.warning("sync_error_type", error_type=etype, count=count)

    newly_synced = {
        full_name_to_url.get(n) or canonicalize_repo_url(f"https://github.com/{n}")
        for n in ok_repos
    }
    newly_synced = {u for u in newly_synced if u}
    updated = set(already_synced) | newly_synced
    save_sync_state(state_file, updated)
    LOGGER.info("sync_state_saved", total_synced=len(updated), newly_added=len(newly_synced))

    return total, success, len(missing_lists)
