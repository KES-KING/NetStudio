"""Bounded, site-scoped projections of server events. Never expose audit details."""
from datetime import timedelta
from urllib.parse import quote

import sqlalchemy as sa

from .auth import fail
from .collection import upsert
from .database import now

LABELS = {
    "device.created": "Cihaz eklendi", "device.connection.updated": "Bağlantı ayarları değişti",
    "inventory.updated": "Envanter güncellendi", "host_key.trusted": "SSH anahtarı onaylandı",
    "job.finished": "Veri toplama işi tamamlandı", "ssh.ended": "SSH oturumu kapandı",
    "user.created": "Kullanıcı oluşturuldu", "user.updated": "Kullanıcı güncellendi",
    "user.deleted": "Kullanıcı silindi", "profile.updated": "Profil güncellendi",
    "password.changed": "Parola değiştirildi", "avatar.updated": "Avatar güncellendi",
    "update.available": "Yeni güncelleme var", "update.queued": "Güncelleme sıraya alındı",
    "update.started": "Güncelleme başladı", "update.finished": "Güncelleme sonucu",
    "update.policy": "Güncelleme tercihi değişti",
}
OUTCOMES = {"succeeded": "Başarılı", "failed": "Başarısız", "partial": "Kısmi", "blocked": "Engellendi",
    "cancelled": "İptal", "recovery_required": "Kurtarma gerekiyor", "queued": "Sırada", "available": "Hazır"}


def scope(store, user):
    audit = store.audit
    devices = sa.select(store.devices.c.id)
    if "*" not in user.site_ids:
        devices = devices.where(store.devices.c.site.in_(user.site_ids))
    admin = "superadmin" in user.roles
    device_events = sa.and_(audit.c.device_id.in_(devices), audit.c.event.in_(list(LABELS)),
        sa.or_(audit.c.event != "ssh.ended", audit.c.user_id == user.user_id))
    personal = sa.and_(audit.c.device_id.is_(None), audit.c.event.in_(list(LABELS)),
        sa.or_(audit.c.user_id == user.user_id, audit.c.target_id == user.user_id, sa.true() if admin else sa.false()))
    system = audit.c.event.in_([key for key in LABELS if key.startswith("update.")])
    return sa.and_(audit.c.occurred_at >= now() - timedelta(days=7), sa.or_(device_events, personal, system))


def after(table, stamp, identifier):
    return sa.or_(table.c.occurred_at > stamp, sa.and_(table.c.occurred_at == stamp, table.c.id > identifier))


def snapshot(store, user):
    table = store.audit
    visible = scope(store, user)
    with store.engine.connect() as conn:
        receipt = conn.execute(sa.select(store.notification_reads).where(store.notification_reads.c.user_id == user.user_id)).mappings().first()
        unread = after(table, receipt["occurred_at"], receipt["event_id"]) if receipt else sa.true()
        rows = conn.execute(sa.select(table.c.id, table.c.event, table.c.outcome, table.c.device_id, table.c.occurred_at,
            store.devices.c.name, unread.label("unread")).outerjoin(store.devices, store.devices.c.id == table.c.device_id)
            .where(visible).order_by(table.c.occurred_at.desc(), table.c.id.desc()).limit(30)).mappings().all()
        count = conn.execute(sa.select(sa.func.count()).select_from(sa.select(table.c.id)
            .where(visible, unread).limit(100).subquery())).scalar_one()
    items = []
    for row in rows:
        href = "/settings/updates" if row["event"].startswith("update.") else f"/devices/{quote(row['device_id'], safe='')}" if row["device_id"] else "/settings"
        items.append(dict(id=row["id"], title=LABELS[row["event"]],
            description=" · ".join(filter(None, [row["name"], OUTCOMES.get(row["outcome"], "")])),
            occurred_at=row["occurred_at"].isoformat(), href=href, unread=bool(row["unread"]),
            severity="error" if row["outcome"] in {"failed", "recovery_required"} else "warning" if row["outcome"] in {"partial", "blocked"} else "info"))
    return dict(items=items, unread_count=count, latest_id=items[0]["id"] if items else None)


def acknowledge(store, user, identifier):
    with store.user_transaction() as conn:
        event = conn.execute(sa.select(store.audit.c.occurred_at, store.audit.c.id)
            .where(store.audit.c.id == identifier, scope(store, user))).first()
        if not event:
            fail("notification_not_found", 404)
        previous = conn.execute(sa.select(store.notification_reads).where(store.notification_reads.c.user_id == user.user_id)).mappings().first()
        if not previous or (event.occurred_at, event.id) > (previous["occurred_at"], previous["event_id"]):
            upsert(conn, store.notification_reads, store.notification_reads.c.user_id == user.user_id,
                dict(user_id=user.user_id, occurred_at=event.occurred_at, event_id=event.id))
