"""Structured audit metadata; never persist arbitrary bodies, headers or terminal input."""
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
import base64
import json
import re
import time
from uuid import uuid4

from fastapi import HTTPException
import sqlalchemy as sa


@dataclass
class AuditRequest:
    started: float = field(default_factory=time.monotonic)
    request_id: str = field(default_factory=lambda: str(uuid4()))
    user_id: str = "anonymous"
    username: str = ""
    roles: list[str] = field(default_factory=list)
    method: str = ""
    route: str = ""
    remote_address: str = ""
    user_agent: str = ""
    status_code: int | None = None
    duration_ms: int | None = None
    error_code: str | None = None
    recorded: bool = False


audit_request: ContextVar[AuditRequest | None] = ContextVar("audit_request", default=None)

# An allowlist, not a best-effort dump-and-redact filter. New fields are omitted
# unless explicitly reviewed here AND supplied by an operation's audit call.
SAFE_KEYS = frozenset({
    "input", "before", "after", "changes", "reason", "username", "display_name", "role", "roles",
    "sites", "enabled", "name", "site", "device_type", "management_address", "ssh_port", "vendor",
    "model", "collector", "credential_configured", "authentication_method", "password_changed",
    "physical_port_count", "interface_count", "binding_count", "observed_at", "source", "action",
    "page", "filters", "q", "type", "status", "minutes", "device_id", "port_id", "node_id",
    "bytes", "width", "height", "duration_seconds", "error_code", "job_id", "result_code",
    "scope", "session_count", "avatar_changed", "confirmation_username", "from", "to", "actor", "event", "outcome", "target_id",
})
SECRET_TEXT = re.compile(
    r"-----BEGIN .*PRIVATE KEY-----|\bBearer\s+\S+|(?:password|passwd|passphrase|secret|token|authorization|cookie|private_key)\s*[:=]",
    re.IGNORECASE,
)


def safe_text(value, limit=512):
    value = str(value)
    if SECRET_TEXT.search(value):
        return "[REDACTED]"
    return re.sub(r"[\x00-\x1f\x7f]", " ", value)[:limit]


def safe_details(value, depth=0):
    if depth > 5:
        return "[TRUNCATED]"
    if isinstance(value, dict):
        return {key: safe_details(item, depth + 1) for key, item in list(value.items())[:80] if key in SAFE_KEYS}
    if isinstance(value, (list, tuple, set)):
        return [safe_details(item, depth + 1) for item in list(value)[:100]]
    if isinstance(value, str):
        return safe_text(value)
    if value is None or type(value) in {bool, int, float}:
        return value
    return "[OMITTED]"


def identify(user):
    if current := audit_request.get():
        current.user_id = user.user_id
        current.username = safe_text(user.username or user.display_name, 160)
        current.roles = sorted(str(role) for role in user.roles)


def encode_cursor(values):
    return base64.urlsafe_b64encode(json.dumps(values, separators=(",", ":")).encode()).decode()


def decode_cursor(value, size=2):
    try:
        if len(value) > 1024:
            raise ValueError
        values = json.loads(base64.b64decode(value, altchars=b"-_", validate=True))
        if not isinstance(values, list) or len(values) != size or any(not isinstance(v, str) or len(v) > 200 for v in values):
            raise ValueError
        return values
    except (ValueError, TypeError, UnicodeError):
        raise HTTPException(422, detail={"code": "invalid_cursor"}) from None


def audit_page(store, *, limit=50, cursor=None, user_id=None, actor=None, event=None, outcome=None,
               target_id=None, since=None, until=None):
    table = store.audit
    query = sa.select(table)
    if actor:
        query = query.where(sa.or_(table.c.user_id == actor, table.c.username == actor))
    if since and since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)
    if until and until.tzinfo is None:
        until = until.replace(tzinfo=timezone.utc)
    for column, value in ((table.c.user_id, user_id), (table.c.event, event),
                          (table.c.outcome, outcome), (table.c.target_id, target_id)):
        if value:
            query = query.where(column == value)
    if since:
        query = query.where(table.c.occurred_at >= since)
    if until:
        query = query.where(table.c.occurred_at <= until)
    if since and until and since > until:
        raise HTTPException(422, detail={"code": "invalid_date_range"})
    if cursor:
        stamp, identifier = decode_cursor(cursor)
        try:
            stamp = datetime.fromisoformat(stamp)
        except ValueError:
            raise HTTPException(422, detail={"code": "invalid_cursor"}) from None
        query = query.where(sa.or_(table.c.occurred_at < stamp,
            sa.and_(table.c.occurred_at == stamp, table.c.id < identifier)))
    with store.engine.connect() as conn:
        rows = [dict(row) for row in conn.execute(query.order_by(table.c.occurred_at.desc(), table.c.id.desc())
            .limit(limit + 1)).mappings()]
    more = len(rows) > limit
    rows = rows[:limit]
    return {"items": rows, "next_cursor": encode_cursor([rows[-1]["occurred_at"].isoformat(), rows[-1]["id"]]) if more else None}
