import json
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Iterable, List, Optional, Set, Tuple

import structlog

from star_organizer.models import (
    ADD_BATCH_SIZE,
    CREATE_BATCH_SIZE,
    GH_TIMEOUT,
    GITHUB_ERROR_RETRY_DELAY,
    LIST_MAX_WORKERS,
    MAX_GQL_RETRIES,
    MAX_SYNC_WORKERS,
    PROGRESS_INTERVAL,
    REPO_LOOKUP_BATCH_SIZE,
    RETRY_BACKOFF_BASE,
)
from star_organizer.rate_limiter import RateLimiter

LOGGER = structlog.get_logger()


def _gql_escape(s: str) -> str:
    return (s or "").replace("\\", "\\\\").replace('"', '\\"')


def _chunked(items: List, size: int) -> Iterable[List]:
    if size <= 0:
        yield items
        return
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _group_errors_by_alias(errors: Optional[List[Dict]]) -> Dict[str, List[str]]:
    grouped: Dict[str, List[str]] = {}
    for err in errors or []:
        path = err.get("path") or []
        alias = str(path[0]) if path else "unknown"
        grouped.setdefault(alias, []).append(err.get("message", ""))
    return grouped


def _is_node_not_found(msg: str) -> bool:
    return "Could not resolve to a node with the global id" in (msg or "")


def _is_resource_limit(msg: str) -> bool:
    return "Resource limits for this query exceeded" in (msg or "")


def _is_github_internal_error(msg: str) -> bool:
    return "Something went wrong while executing your query" in (msg or "")


def _classify_error(msg: str) -> str:
    m = msg or ""
    if not m or m == "no error details available":
        return "unknown_error"
    if "Could not resolve to a node" in m or "not found" in m.lower():
        return "not_found"
    if "Resource limits" in m:
        return "rate_limit"
    if "403" in m or "forbidden" in m.lower():
        return "permission_denied"
    if "timeout" in m.lower():
        return "timeout"
    if "Something went wrong while executing your query" in m:
        return "github_internal_error"
    return m


def _run_gh(cmd: List[str], timeout: int = 30) -> Tuple[bool, str, str]:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, "", str(e)


def _run_graphql(query: str, timeout: int = GH_TIMEOUT, limiter: Optional[RateLimiter] = None) -> Tuple[bool, str, str]:
    if limiter:
        limiter.acquire()
    return _run_gh(["gh", "api", "graphql", "-f", f"query={query}"], timeout=timeout)


def _run_graphql_with_retries(
    query: str,
    *,
    timeout: int = GH_TIMEOUT,
    limiter: Optional[RateLimiter] = None,
    max_retries: int = MAX_GQL_RETRIES,
) -> Tuple[bool, Dict, str]:
    attempt = 0
    while True:
        ok, stdout, stderr = _run_graphql(query, timeout=timeout, limiter=limiter)
        try:
            if stdout:
                data = json.loads(stdout)
                return True, data, stderr if not ok else ""
            raise ValueError("empty_stdout")
        except Exception as e:
            attempt += 1
            if attempt > max_retries:
                return False, {}, stderr or str(e)
            sleep_for = RETRY_BACKOFF_BASE ** (attempt - 1)
            if limiter:
                limiter.slow_down()
            LOGGER.warning("graphql_retry", attempt=attempt, sleep=f"{sleep_for:.1f}s")
            time.sleep(sleep_for)


def parse_repo_url(url: str) -> Tuple[str, str]:
    s = url.strip().replace(".git", "")
    m = re.search(r"github\.com[:/]+([^/]+)/([^/?#]+)", s, re.IGNORECASE)
    if not m:
        return "", ""
    return m.group(1), m.group(2)


def get_all_lists(limiter: Optional[RateLimiter] = None) -> List[Dict]:
    query = """
    query {
        viewer {
            lists(first: 50) {
                nodes { id name description }
            }
        }
    }
    """
    ok, data, err = _run_graphql_with_retries(query, limiter=limiter)
    if not ok:
        LOGGER.error("get_lists_failed", stderr=err)
        return []
    try:
        return (data.get("data") or {}).get("viewer", {}).get("lists", {}).get("nodes", []) or []
    except Exception:
        return []


def delete_list(list_id: str, list_name: str, limiter: RateLimiter) -> bool:
    if not list_id:
        return False
    mutation = f'''
    mutation {{
        deleteUserList(input: {{ listId: "{_gql_escape(list_id)}" }}) {{
            clientMutationId
        }}
    }}
    '''
    ok, data, err = _run_graphql_with_retries(mutation, limiter=limiter)
    if not ok:
        if _is_node_not_found(err):
            return True
        LOGGER.error("list_delete_failed", name=list_name, reason=err)
        return False

    errors = data.get("errors") or []
    if errors:
        msgs = [e.get("message", "") for e in errors if isinstance(e, dict)]
        if msgs and all(_is_node_not_found(m) for m in msgs):
            return True
        LOGGER.error("list_delete_failed", name=list_name, reason="; ".join(msgs))
        return False

    if (data.get("data") or {}).get("deleteUserList") is not None:
        LOGGER.info("list_deleted", name=list_name)
        return True
    return False


def delete_all_lists(limiter: RateLimiter) -> int:
    existing = get_all_lists(limiter=limiter)
    LOGGER.info("existing_lists_found", count=len(existing))

    total_deleted = 0
    for round_num in range(1, 6):
        if not existing:
            break
        LOGGER.info("delete_round", round=round_num, remaining=len(existing))
        with ThreadPoolExecutor(max_workers=min(LIST_MAX_WORKERS, len(existing))) as ex:
            futs = [ex.submit(delete_list, lst.get("id", ""), lst.get("name", ""), limiter) for lst in existing]
            for f in as_completed(futs):
                if f.result():
                    total_deleted += 1
        time.sleep(1.0)
        existing = get_all_lists(limiter=limiter)

    if existing:
        LOGGER.error("delete_incomplete", remaining=len(existing))
    else:
        LOGGER.info("all_lists_deleted", count=total_deleted)
    return total_deleted


def create_lists(
    categories: List[Tuple[str, str, str]],
    limiter: RateLimiter,
) -> Dict[str, str]:
    if not categories:
        return {}

    batches = list(_chunked(categories, CREATE_BATCH_SIZE))

    def worker(batch: List[Tuple[str, str, str]]) -> Dict[str, str]:
        if not batch:
            return {}
        alias_to_cat: Dict[str, str] = {}
        lines = ["mutation {"]
        for i, (cat_key, name, desc) in enumerate(batch):
            alias = f"c{i}"
            alias_to_cat[alias] = cat_key
            lines.append(
                f'  {alias}: createUserList(input: {{ name: "{_gql_escape(name)}", '
                f'description: "{_gql_escape((desc or "").replace(chr(10), " "))}" }}) '
                f"{{ list {{ id name }} }}"
            )
        lines.append("}")

        ok, data, err = _run_graphql_with_retries("\n".join(lines), limiter=limiter)
        if not ok or _is_resource_limit(err) or any(
            _is_resource_limit((e or {}).get("message", "")) for e in (data.get("errors") or [])
        ):
            if len(batch) > 1:
                mid = len(batch) // 2
                out: Dict[str, str] = {}
                out.update(worker(batch[:mid]))
                out.update(worker(batch[mid:]))
                return out
            for cat_key, name, _ in batch:
                LOGGER.error("list_create_failed", name=name, category=cat_key)
            return {}

        errors_by_alias = _group_errors_by_alias(data.get("errors"))
        payload = data.get("data") or {}
        out: Dict[str, str] = {}
        for alias, cat_key in alias_to_cat.items():
            node = payload.get(alias) or {}
            lst = node.get("list") if isinstance(node, dict) else None
            list_id = (lst or {}).get("id") if isinstance(lst, dict) else None
            if list_id:
                out[cat_key] = list_id
                LOGGER.info("list_created", name=(lst or {}).get("name", ""), category=cat_key)
            else:
                msgs = errors_by_alias.get(alias, [])
                LOGGER.error("list_create_failed", category=cat_key, reason="; ".join(msgs) or "no id")
        return out

    list_ids: Dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=min(LIST_MAX_WORKERS, len(batches))) as ex:
        for fut in as_completed([ex.submit(worker, b) for b in batches]):
            list_ids.update(fut.result())
    return list_ids


def fetch_repo_ids(
    repo_pairs: List[Tuple[str, str]],
    limiter: RateLimiter,
) -> Dict[Tuple[str, str], str]:
    if not repo_pairs:
        return {}

    batches = list(_chunked(repo_pairs, REPO_LOOKUP_BATCH_SIZE))

    def worker(batch: List[Tuple[str, str]]) -> Dict[Tuple[str, str], str]:
        if not batch:
            return {}
        alias_map: Dict[str, Tuple[str, str]] = {}
        lines = ["query {"]
        for i, (owner, name) in enumerate(batch):
            alias = f"r{i}"
            alias_map[alias] = (owner, name)
            lines.append(
                f'  {alias}: repository(owner: "{_gql_escape(owner)}", name: "{_gql_escape(name)}") '
                f"{{ id nameWithOwner }}"
            )
        lines.append("}")

        ok, data, err = _run_graphql_with_retries("\n".join(lines), limiter=limiter)
        if not ok or _is_resource_limit(err) or any(
            _is_resource_limit((e or {}).get("message", "")) for e in (data.get("errors") or [])
        ):
            if len(batch) > 1:
                mid = len(batch) // 2
                out: Dict[Tuple[str, str], str] = {}
                out.update(worker(batch[:mid]))
                out.update(worker(batch[mid:]))
                return out
            return {}

        errors_by_alias = _group_errors_by_alias(data.get("errors"))
        payload = data.get("data") or {}
        out: Dict[Tuple[str, str], str] = {}
        for alias, (owner, name) in alias_map.items():
            node = payload.get(alias)
            if node and isinstance(node, dict) and node.get("id"):
                out[(owner, name)] = node["id"]
            else:
                msgs = errors_by_alias.get(alias, [])
                if msgs:
                    LOGGER.warning("repo_not_found", repo=f"{owner}/{name}", reason="; ".join(msgs))
        return out

    repo_ids: Dict[Tuple[str, str], str] = {}
    with ThreadPoolExecutor(max_workers=min(MAX_SYNC_WORKERS, len(batches))) as ex:
        for fut in as_completed([ex.submit(worker, b) for b in batches]):
            repo_ids.update(fut.result())
    return repo_ids


def add_repos_to_lists(
    ops: List[Tuple[str, str, str, str]],
    limiter: RateLimiter,
) -> Tuple[int, int, Dict[str, int], Dict[str, int], Set[str]]:
    if not ops:
        return 0, 0, {}, {}, set()

    batches = list(_chunked(ops, ADD_BATCH_SIZE))

    def worker(batch: List[Tuple[str, str, str, str]]) -> Tuple[int, int, Dict[str, int], Dict[str, int], Set[str]]:
        if not batch:
            return 0, 0, {}, {}, set()

        alias_map: Dict[str, Tuple[str, str]] = {}
        lines = ["mutation {"]
        for i, (cat_name, repo_id, repo_full, list_id) in enumerate(batch):
            alias = f"a{i}"
            alias_map[alias] = (repo_full, cat_name)
            lines.append(
                f'  {alias}: updateUserListsForItem(input: {{ itemId: "{_gql_escape(repo_id)}", '
                f'listIds: ["{_gql_escape(list_id)}"], suggestedListIds: [] }}) '
                f"{{ clientMutationId }}"
            )
        lines.append("}")
        mutation = "\n".join(lines)

        ok, data, err = _run_graphql_with_retries(mutation, limiter=limiter)

        if _is_github_internal_error(err) or any(
            _is_github_internal_error((e or {}).get("message", "")) for e in (data.get("errors") or [])
        ):
            time.sleep(GITHUB_ERROR_RETRY_DELAY)
            limiter.slow_down()
            ok, data, err = _run_graphql_with_retries(mutation, limiter=limiter)

        if not ok or _is_resource_limit(err) or any(
            _is_resource_limit((e or {}).get("message", "")) for e in (data.get("errors") or [])
        ):
            if len(batch) > 1:
                mid = len(batch) // 2
                a1, s1, pc1, et1, ok1 = worker(batch[:mid])
                a2, s2, pc2, et2, ok2 = worker(batch[mid:])
                pc = dict(pc1)
                for k, v in pc2.items():
                    pc[k] = pc.get(k, 0) + v
                et = dict(et1)
                for k, v in et2.items():
                    et[k] = et.get(k, 0) + v
                return a1 + a2, s1 + s2, pc, et, ok1 | ok2

            error_types: Dict[str, int] = {}
            for cat_name, _, repo_full, _ in batch:
                ec = _classify_error(err or "batch failed")
                error_types[ec] = error_types.get(ec, 0) + 1
                LOGGER.error("repo_add_failed", repo=repo_full, category=cat_name, error_type=ec)
            return len(batch), 0, {}, error_types, set()

        errors_by_alias = _group_errors_by_alias(data.get("errors"))
        payload = data.get("data") or {}
        succeeded = 0
        per_cat: Dict[str, int] = {}
        error_types: Dict[str, int] = {}
        ok_repos: Set[str] = set()

        for alias, (repo_full, cat_name) in alias_map.items():
            if payload.get(alias) is not None:
                succeeded += 1
                per_cat[cat_name] = per_cat.get(cat_name, 0) + 1
                ok_repos.add(repo_full)
            else:
                msgs = errors_by_alias.get(alias, [])
                ec = _classify_error("; ".join(msgs) if msgs else err or "unknown")
                error_types[ec] = error_types.get(ec, 0) + 1
                LOGGER.error("repo_add_failed", repo=repo_full, category=cat_name, error_type=ec)

        return len(batch), succeeded, per_cat, error_types, ok_repos

    attempted_total = 0
    succeeded_total = 0
    per_cat_total: Dict[str, int] = {}
    error_types_total: Dict[str, int] = {}
    ok_repos_total: Set[str] = set()
    next_progress = PROGRESS_INTERVAL

    with ThreadPoolExecutor(max_workers=min(MAX_SYNC_WORKERS, len(batches))) as ex:
        for fut in as_completed([ex.submit(worker, b) for b in batches]):
            attempted, succeeded, pc, et, ok_r = fut.result()
            attempted_total += attempted
            succeeded_total += succeeded
            ok_repos_total |= ok_r
            for k, v in pc.items():
                per_cat_total[k] = per_cat_total.get(k, 0) + v
            for k, v in et.items():
                error_types_total[k] = error_types_total.get(k, 0) + v
            while attempted_total >= next_progress:
                LOGGER.info("sync_progress", total=attempted_total, success=succeeded_total)
                next_progress += PROGRESS_INTERVAL

    return attempted_total, succeeded_total, per_cat_total, error_types_total, ok_repos_total


def format_list_name(category: str) -> str:
    return category.replace("_", " ").title()


def resolve_list_ids(
    organized_stars: Dict,
    limiter: RateLimiter,
    needed_categories: Optional[set] = None,
) -> Dict[str, str]:
    existing = get_all_lists(limiter=limiter)
    existing_by_lower = {
        (lst.get("name", "") or "").strip().lower(): (lst.get("id", "") or "")
        for lst in existing
        if isinstance(lst, dict)
    }

    list_ids: Dict[str, str] = {}
    to_create: List[Tuple[str, str, str]] = []

    for cat_name, cat_data in organized_stars.items():
        if needed_categories is not None and cat_name not in needed_categories:
            continue
        if not cat_data.get("repos") and not cat_data.get("description"):
            continue
        display = format_list_name(cat_name)
        eid = existing_by_lower.get(display.strip().lower(), "")
        if eid:
            list_ids[cat_name] = eid
        else:
            to_create.append((cat_name, display, cat_data.get("description", "")))

    if to_create:
        list_ids.update(create_lists(to_create, limiter=limiter))

    return list_ids
