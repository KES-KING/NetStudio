"""Public GitHub metadata + durable policy. This module cannot execute host commands."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
import re
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, HTTPRedirectHandler
from uuid import uuid4

import sqlalchemy as sa

from .auth import fail
from .database import now
from .auditing import safe_text

REPOSITORY = "KES-KING/NetStudio"
REPOSITORY_URL = f"https://github.com/{REPOSITORY}"
SHA = re.compile(r"^[0-9a-f]{40}$")
ACTIVE = {"queued", "building", "draining", "backing_up", "migrating", "deploying", "verifying"}


def defaults():
    revision = os.getenv("STOCC_BUILD_REVISION", "")
    return dict(automatic=False, policy_actor=None, installed_revision=revision if SHA.fullmatch(revision) else None,
        commits=[], latest_revision=None, checked_at=None, next_check=0, etag=None, error_code=None,
        check_owner=None, check_until=0, agent_id=None, agent_seen=0, agent_ready=False,
        active_run=None, maintenance=False, recovery_required=False)


def read(store, conn=None):
    def get(connection):
        value = connection.execute(sa.select(store.system_update.c.payload).where(store.system_update.c.id == 1)).scalar_one_or_none()
        return {**defaults(), **(value or {})}
    if conn is not None:
        return get(conn)
    with store.engine.connect() as connection:
        return get(connection)


@contextmanager
def locked(store):
    # Short serialized writes only. Network/build/migration never hold this lock.
    with store.user_transaction() as conn:
        exists = conn.execute(sa.select(store.system_update.c.id).where(store.system_update.c.id == 1)).first()
        state = read(store, conn)
        yield conn, state
        if exists:
            conn.execute(store.system_update.update().where(store.system_update.c.id == 1).values(payload=state))
        else:
            conn.execute(store.system_update.insert().values(id=1, payload=state))


def agent_online(state):
    return bool(state["agent_ready"] and 0 <= time.time() - state["agent_seen"] < 45)


def available(state):
    return bool(state["installed_revision"] and state["latest_revision"] and state["installed_revision"] != state["latest_revision"])


def maintenance(store):
    state = read(store)
    # Deliberately fail closed after a host crash; never resume writes into a
    # possibly half-migrated deployment just because its lease expired.
    return state["maintenance"] or state["recovery_required"]


def public_state(store, *, manager=False):
    state = read(store)
    with store.engine.connect() as conn:
        runs = [dict(row) for row in conn.execute(sa.select(store.update_runs)
            .order_by(store.update_runs.c.created_at.desc()).limit(20)).mappings()]
    for run in runs:
        run.pop("actor", None)
    return {key: state[key] for key in ("automatic", "installed_revision", "latest_revision", "checked_at",
        "error_code", "maintenance", "recovery_required")} | {
        "repository": REPOSITORY, "repository_url": REPOSITORY_URL, "branch": "main",
        "available": available(state), "agent_online": agent_online(state),
        "commits": state["commits"], "runs": runs, "can_manage": manager,
        "next_check_at": datetime.fromtimestamp(state["next_check"], timezone.utc).isoformat() if state["next_check"] else None,
    }


def allowed_actor(store, conn, actor):
    row = conn.execute(sa.select(store.users.c.roles, store.users.c.enabled).where(store.users.c.id == actor)).first()
    return bool(row and row.enabled and "superadmin" in row.roles)


def enqueue_update(store, conn, state, actor, automatic=False):
    if state["recovery_required"]:
        fail("update_recovery_required", 409)
    if state["active_run"]:
        return state["active_run"]
    if not agent_online(state):
        fail("update_agent_unavailable", 409)
    if not state["installed_revision"]:
        fail("update_revision_unknown", 409)
    if not available(state) or state["error_code"] or not state["checked_at"] or time.time() - datetime.fromisoformat(state["checked_at"]).timestamp() > 1800:
        fail("update_check_required", 409)
    if not allowed_actor(store, conn, actor):
        fail("forbidden", 403)
    identifier = str(uuid4())
    conn.execute(store.update_runs.insert().values(id=identifier, revision=state["latest_revision"], status="queued",
        actor=actor, automatic=automatic, created_at=now(), updated_at=now()))
    state["active_run"] = identifier
    store.record(actor, "update.queued", "queued", target_type="update", target_id=identifier, conn=conn)
    return identifier


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def github_commits(etag=None):
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "NetStudio-update-checker"}
    if etag:
        headers["If-None-Match"] = etag
    request = Request(f"https://api.github.com/repos/{REPOSITORY}/commits?sha=main&per_page=30", headers=headers)
    try:
        with build_opener(NoRedirect()).open(request, timeout=12) as response:
            body = response.read(1_000_001)
            if len(body) > 1_000_000:
                raise ValueError("github_response_too_large")
            payload = json.loads(body)
            if not isinstance(payload, list) or not 1 <= len(payload) <= 30:
                raise ValueError("github_invalid_response")
            commits = []
            for item in payload:
                sha = item["sha"]
                if not isinstance(sha, str) or not SHA.fullmatch(sha):
                    raise ValueError("github_invalid_revision")
                commit = item["commit"]
                message = str(commit["message"])
                published = datetime.fromisoformat(commit["committer"]["date"].replace("Z", "+00:00"))
                if published.tzinfo is None:
                    raise ValueError("github_invalid_date")
                commits.append(dict(sha=sha, title=safe_text(message.splitlines()[0] if message else sha[:12], 200),
                    description=safe_text(message, 4000), author=safe_text(commit["author"]["name"], 120),
                    committed_at=published.isoformat(), url=f"{REPOSITORY_URL}/commit/{sha}"))
            return commits, response.headers.get("ETag", "")[:300], None, 600
    except HTTPError as exc:
        if exc.code == 304:
            return None, etag, None, 600
        wait = 600
        if exc.code in {403, 429}:
            try:
                wait = max(wait, int(exc.headers.get("Retry-After", "0")), int(exc.headers.get("X-RateLimit-Reset", "0")) - int(time.time()))
            except (ValueError, TypeError):
                pass
        return None, None, "github_rate_limited" if exc.code in {403, 429} else "github_unavailable", min(wait, 86400)
    except (URLError, TimeoutError, ValueError, KeyError, TypeError, IndexError, OSError):
        return None, None, "github_unavailable", 600


def check(store, *, requested=False, fetch=None):
    fetch = fetch or github_commits
    owner = str(uuid4())
    with locked(store) as (conn, state):
        stamp = time.time()
        if state["check_until"] > stamp or state["next_check"] > stamp:
            return False
        state.update(check_owner=owner, check_until=stamp + 30)
        etag = state["etag"]
    commits, new_etag, error, delay = fetch(etag)
    with locked(store) as (conn, state):
        if state["check_owner"] != owner:
            return False
        old_head = state["latest_revision"]
        state.update(check_owner=None, check_until=0, next_check=time.time() + max(60, delay), error_code=error)
        if not error:
            state["checked_at"] = now().isoformat()
            state["etag"] = new_etag
            if commits is not None:
                state.update(commits=commits, latest_revision=commits[0]["sha"])
            if available(state) and old_head != state["latest_revision"]:
                store.record("system:updates", "update.available", "available", target_type="revision", target_id=state["latest_revision"], conn=conn)
            failed = conn.execute(sa.select(store.update_runs.c.id).where(store.update_runs.c.revision == state["latest_revision"],
                store.update_runs.c.status.in_(("failed", "recovery_required", "cancelled")))).first()
            if state["automatic"] and available(state) and agent_online(state) and not state["active_run"] and not failed and not state["recovery_required"]:
                if allowed_actor(store, conn, state["policy_actor"]):
                    enqueue_update(store, conn, state, state["policy_actor"], automatic=True)
        if requested:
            store.record("system:updates", "update.checked", "failed" if error else "succeeded", conn=conn)
    return True
