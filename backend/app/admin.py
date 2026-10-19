"""Interactive administration; passwords are never command-line arguments."""
import argparse
import getpass
from uuid import uuid4

import sqlalchemy as sa

from .auth import hasher
from .database import Store, now
from .users import UserCreate, audit_user
from .vault import CredentialVault


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    user = sub.add_parser("create-user")
    user.add_argument("--username", required=True)
    user.add_argument("--role", choices=["superadmin", "engineer", "viewer", "admin", "operator"], default="superadmin")
    user.add_argument("--site", action="append", required=True)
    revoke = sub.add_parser("disable-user")
    revoke.add_argument("--username", required=True)
    sub.add_parser("rotate-secrets")
    args = parser.parse_args()
    store = Store()
    if args.command == "create-user":
        password = getpass.getpass("Yeni parola (en az 12 karakter): ")
        confirmation = getpass.getpass("Parola tekrar: ")
        if len(password) < 12 or password != confirmation:
            raise SystemExit("Parola eşleşmeli ve en az 12 karakter olmalı.")
        role = {"admin": "superadmin", "operator": "engineer"}.get(args.role, args.role)
        value = UserCreate(username=args.username, role=role, sites=args.site, password=password)
        encoded = hasher.hash(password)
        identifier = str(uuid4())
        with store.user_transaction() as conn:
            if conn.execute(sa.select(store.users.c.id).where(store.users.c.username == args.username)).first():
                raise SystemExit("Kullanıcı zaten var; üzerine yazılmadı.")
            conn.execute(store.users.insert().values(id=identifier, username=value.username, password_hash=encoded,
                display_name=value.username[:100], roles=[value.role], sites=value.sites, enabled=True, created_at=now(), updated_at=now()))
            store.record("local-admin", "user.created", "succeeded", target_type="user", target_id=identifier,
                details={"input": {"username": value.username, "role": value.role, "sites": value.sites}, "source": "local-cli"}, conn=conn)
        print("Kullanıcı oluşturuldu.")
    elif args.command == "disable-user":
        with store.user_transaction() as conn:
            row = conn.execute(sa.select(store.users).where(store.users.c.username == args.username)).mappings().one()
            identifier = row["id"]
            active = conn.execute(sa.select(store.users.c.roles).where(store.users.c.enabled.is_(True))).scalars()
            if row["enabled"] and "superadmin" in row["roles"] and sum("superadmin" in roles for roles in active) <= 1:
                raise SystemExit("Son aktif superadmin devre dışı bırakılamaz.")
            conn.execute(store.users.update().where(store.users.c.id == identifier).values(enabled=False))
            conn.execute(store.sessions.delete().where(store.sessions.c.user_id == identifier))
            store.record("local-admin", "user.disabled", "succeeded", target_type="user", target_id=identifier,
                details={"before": audit_user(row), "source": "local-cli"}, conn=conn)
        print("Kullanıcı ve oturumları devre dışı bırakıldı.")
    else:
        # Deploy a keyring with old keys retained + a new active key before this.
        vault = CredentialVault(store)
        with store.engine.connect() as conn:
            ids = conn.execute(sa.select(store.secrets.c.device_id)).scalars().all()
        envelopes = [vault.encode(identifier, vault.get(identifier)) for identifier in ids]
        with store.engine.begin() as conn:
            for envelope in envelopes:
                identifier = envelope.pop("device_id")
                conn.execute(store.secrets.update().where(store.secrets.c.device_id == identifier).values(**envelope))
        store.record("local-admin", "secrets.rotated", "succeeded")
        print(f"{len(envelopes)} kayıt etkin anahtarla yeniden şifrelendi.")


if __name__ == "__main__":
    main()
