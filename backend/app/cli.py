"""Operational CLI: ``python -m app.cli <command>``.

  create-user  --email E --name N --role admin|user|viewer [--password P]   (password is prompted/generated if omitted)
  migrate                                                                   (alembic upgrade head)
"""
from __future__ import annotations

import argparse
import asyncio
import getpass
import secrets
import sys

from sqlalchemy import select


async def _create_user(email: str, name: str, role: str, password: str | None) -> str:
    from app.auth.password import hash_password
    from app.database import async_session_maker
    from app.models import User

    generated = False
    if not password:
        password = secrets.token_urlsafe(16) + "!A1"
        generated = True
    if len(password) < 12:
        raise SystemExit("password must be at least 12 characters")
    async with async_session_maker() as db:
        existing = await db.scalar(select(User).where(User.email == email))
        if existing:
            raise SystemExit(f"user {email} already exists")
        db.add(User(email=email, name=name, role=role, password_hash=hash_password(password)))
        await db.commit()
    return password if generated else ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    cu = sub.add_parser("create-user")
    cu.add_argument("--email", required=True)
    cu.add_argument("--name", required=True)
    cu.add_argument("--role", choices=["admin", "user", "viewer"], default="user")
    cu.add_argument("--password", default=None, help="omit to be prompted; use --generate for a random one")
    cu.add_argument("--generate", action="store_true")
    sub.add_parser("migrate")
    args = parser.parse_args(argv)

    if args.cmd == "migrate":
        from app.migrate import upgrade_to_head

        print(upgrade_to_head())
        return 0
    if args.cmd == "create-user":
        pw = None if args.generate else (args.password or getpass.getpass("Password (min 12 chars): "))
        generated = asyncio.run(_create_user(args.email, args.name, args.role, pw))
        print(f"created {args.role} {args.email}")
        if generated:
            print(f"generated password: {generated}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
