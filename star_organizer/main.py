import argparse
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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


def _phase_1_fetch_and_load(
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


def _phase_2_metadata(
    repos: List[dict],
    organized: OrganizedStarLists,
    reset: bool,
) -> Tuple[List[RepoMetadata], List[RepoMetadata]]:
    LOGGER.info("phase_2_metadata_extraction")

    already_categorized = extract_all_repo_urls(organized) if not reset else set()
    all_metadata = extract_repos_metadata(repos)
    metadata_by_url = {m["url"]: m for m in all_metadata}

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


def _phase_3_categorize(
    all_metadata: List[RepoMetadata],
    new_metadata: List[RepoMetadata],
    organized: OrganizedStarLists,
    reset: bool,
    output_file: str,
) -> OrganizedStarLists:
    LOGGER.info("phase_3_categorization")

    need_categories = not organized or len(organized) < MAX_GITHUB_LISTS or reset
    if need_categories:
        LOGGER.info("creating_new_categories", using_repos=len(all_metadata))
        categories = create_categories(all_metadata)

        old_repos_by_url: Dict[str, dict] = {}
        if not reset:
            for data in organized.values():
                for repo in data.get("repos", []):
                    if isinstance(repo, dict) and repo.get("url"):
                        old_repos_by_url[repo["url"]] = repo

        organized = {
            name: {"description": desc, "repos": []}
            for name, desc in categories.items()
        }

        if old_repos_by_url:
            first_cat = next(iter(organized.keys()))
            for repo in old_repos_by_url.values():
                organized[first_cat]["repos"].append(repo)

        save_organized_stars(output_file, organized)
        LOGGER.info("categories_saved", count=len(organized))

    if not new_metadata:
        LOGGER.info("no_new_repos_to_categorize")
        return organized

    count = categorize_repos(new_metadata, organized, save_organized_stars, output_file)
    LOGGER.info("phase_3_complete", categorized=count)
    return organized


def _phase_4_sync(
    organized: OrganizedStarLists,
    already_synced: Set[str],
    reset: bool,
    state_file: str,
) -> None:
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
        return

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

    for cat_name, repo_full, repo_url in tasks:
        list_id = list_ids.get(cat_name, "")
        if not list_id:
            continue
        owner, name = repo_full.split("/", 1)
        rid = repo_ids.get((owner, name), "")
        if not rid:
            skipped += 1
            continue
        ops.append((cat_name, rid, repo_full, list_id))
        full_name_to_url[repo_full] = repo_url

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


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Unified pipeline: organize GitHub stars and sync to GitHub Lists.")
    parser.add_argument("--reset", action="store_true", help="Full reset: delete lists, re-categorize, re-sync")
    parser.add_argument("--backup", action="store_true", help="Backup organized_stars.json before reset")
    parser.add_argument("--organize-only", action="store_true", help="Only organize, skip GitHub sync")
    parser.add_argument("--sync-only", action="store_true", help="Only sync existing organized_stars.json")
    parser.add_argument("--test-limit", type=int, default=0, help="Limit starred repos fetched (for testing)")
    parser.add_argument("--state-file", default=SYNC_STATE_FILE, help="Path to sync state file")
    parser.add_argument("--output-file", default=OUTPUT_FILE, help="Path to organized_stars.json")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    if not GITHUB_TOKEN:
        LOGGER.error("missing_github_token")
        sys.exit(1)

    if not args.sync_only and not OPENAI_API_KEY:
        LOGGER.error("missing_openai_api_key")
        sys.exit(1)

    LOGGER.info("pipeline_start", reset=args.reset, test_limit=args.test_limit or "all")

    if args.reset and args.backup and os.path.exists(args.output_file):
        backup = f"{args.output_file}.backup.{int(time.time())}"
        try:
            with open(args.output_file, "r", encoding="utf-8") as src:
                with open(backup, "w", encoding="utf-8") as dst:
                    dst.write(src.read())
            LOGGER.info("backup_created", file=backup)
        except Exception as e:
            LOGGER.error("backup_failed", error=str(e))

    if args.sync_only:
        organized = load_organized_stars(args.output_file)
        if not organized:
            LOGGER.error("no_organized_data", file=args.output_file)
            sys.exit(1)
        if len(organized) < MAX_GITHUB_LISTS:
            LOGGER.warning("incomplete_categories", count=len(organized), expected=MAX_GITHUB_LISTS)
        already_synced = set() if args.reset else load_sync_state(args.state_file)
        _phase_4_sync(organized, already_synced, args.reset, args.state_file)
        return

    repos, organized, already_synced = _phase_1_fetch_and_load(
        args.reset, args.state_file, args.output_file, args.test_limit
    )

    if not repos:
        LOGGER.error("no_repos_fetched")
        sys.exit(1)

    all_metadata, new_metadata = _phase_2_metadata(repos, organized, args.reset)

    organized = _phase_3_categorize(all_metadata, new_metadata, organized, args.reset, args.output_file)

    if args.organize_only:
        LOGGER.info("organize_only_done", categories=len(organized))
        return

    _phase_4_sync(organized, already_synced, args.reset, args.state_file)

    total_repos = sum(len(d.get("repos", [])) for d in organized.values())
    LOGGER.info("pipeline_complete", categories=len(organized), total_repos=total_repos)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        LOGGER.warning("interrupted")
    except Exception as e:
        LOGGER.error("unexpected_error", error=str(e))
        import traceback
        traceback.print_exc()
