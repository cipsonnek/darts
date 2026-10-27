"""Operator accounts on the central server: ``python -m backend.users``.

    python -m backend.users add jan              # asks for the password twice
    python -m backend.users passwd jan           # new password (signs out jan everywhere)
    python -m backend.users disable jan | enable jan
    python -m backend.users list

Uses the central server's configuration (configs/central.yaml) unless --config is given.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys


def _ask_password() -> str:
    env = os.environ.get("DARTSENSE_NEW_PASSWORD")
    if env:
        return env
    a = getpass.getpass("Hasło: ")
    b = getpass.getpass("Powtórz hasło: ")
    if a != b:
        sys.exit("Hasła się różnią.")
    return a


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m backend.users", description="Konta panelu operatora")
    ap.add_argument("--config", default="configs/central.yaml", help="warstwa konfiguracji serwera centralnego")
    sub = ap.add_subparsers(dest="cmd", required=True)
    add = sub.add_parser("add", help="nowe konto")
    add.add_argument("username")
    add.add_argument("--name", default="", help="imię i nazwisko (wyświetlane w panelu)")
    for cmd in ("passwd", "disable", "enable"):
        sub.add_parser(cmd).add_argument("username")
    sub.add_parser("list")
    args = ap.parse_args()
    # Polish messages through pipes and SSH sessions (a Windows pipe defaults to cp1250).
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    os.environ["DARTSENSE_CONFIG"] = args.config
    from backend.database import Database
    from backend.services.auth_service import AuthError, AuthService
    from backend.settings import load_settings

    settings = load_settings()
    db = Database(settings.database.url)
    db.migrate()
    svc = AuthService(db)
    try:
        if args.cmd == "add":
            u = svc.create_user(args.username, _ask_password(), args.name)
            print(f"Utworzono konto: {u['username']}")
        elif args.cmd == "passwd":
            svc.set_password(args.username, _ask_password())
            print("Hasło zmienione.")
        elif args.cmd in ("disable", "enable"):
            svc.set_active(args.username, args.cmd == "enable")
            print("Konto " + ("włączone." if args.cmd == "enable" else "wyłączone."))
        else:
            for u in svc.list_users():
                state = "" if u["active"] else "  (wyłączone)"
                print(f"{u['username']:<24} {u['display_name']:<30} ostatnio: {u['last_login_at'] or '—'}{state}")
    except AuthError as e:
        sys.exit(f"Błąd: {e}")


if __name__ == "__main__":
    main()
