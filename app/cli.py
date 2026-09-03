"""User administration from the server shell.

    python -m app.cli user add vasya
    python -m app.cli user list
    python -m app.cli user disable vasya

This is the whole of user management: there is no registration endpoint and no
admin API. An endpoint that does not exist cannot be found, guessed at, or left
misconfigured, and for a band-sized deployment the account list changes a few
times a year — ssh is not the bottleneck. `User.is_admin` already exists for
the day a web admin arrives with invitations (roadmap step 3), so that step is
a routing change rather than a migration.

Run from the backend directory so DATABASE_URL resolves the same way the
server resolves it, or set DATABASE_URL explicitly.
"""

from __future__ import annotations

import argparse
import getpass
import sys
from datetime import datetime
from pathlib import Path

from sqlmodel import select

from .core.config import settings
from .core.database import session_scope
from .modules.auth.models import AuthSession, User
from .modules.auth.passwords import MIN_PASSWORD_LENGTH, hash_password
from .modules.auth.sessions import revoke_all_for_user
from .tables import init_database


def _normalise(username: str) -> str:
    return username.strip().lower()


def _find(session, username: str) -> User | None:
    return session.exec(select(User).where(User.username == _normalise(username))).first()


def _read_new_password() -> str:
    """Ask twice, never echo, never accept via argv.

    A password passed as an argument lands in shell history and in the process
    list, where any other user on the box can read it while it runs.
    """

    if not sys.stdin.isatty():
        # Allows `echo 'secret' | python -m app.cli user add vasya` for
        # provisioning scripts, where there is no terminal to prompt on.
        password = sys.stdin.readline().rstrip("\n")
        if len(password) < MIN_PASSWORD_LENGTH:
            raise SystemExit(f"Пароль короче {MIN_PASSWORD_LENGTH} символов.")
        return password

    while True:
        password = getpass.getpass("Пароль: ")
        if len(password) < MIN_PASSWORD_LENGTH:
            print(f"Слишком короткий пароль — нужно не меньше {MIN_PASSWORD_LENGTH} символов.")
            continue
        if password != getpass.getpass("Повторите пароль: "):
            print("Пароли не совпадают.")
            continue
        return password


def cmd_add(args: argparse.Namespace) -> int:
    username = _normalise(args.username)
    if not username:
        print("Пустой логин.", file=sys.stderr)
        return 1

    with session_scope() as session:
        if _find(session, username):
            print(f"Пользователь {username!r} уже есть.", file=sys.stderr)
            return 1

        password = _read_new_password()
        user = User(
            username=username,
            password_hash=hash_password(password),
            display_name=(args.display_name or args.username).strip()[:60],
            is_admin=args.admin,
        )
        session.add(user)
        # Read before the block ends: session_scope commits and closes, which
        # expires the instance and makes every attribute a fresh query.
        display_name = user.display_name

    print(f"Создан пользователь {username!r} (отображается как {display_name!r}).")
    return 0


def cmd_list(_args: argparse.Namespace) -> int:
    now = datetime.utcnow()
    with session_scope() as session:
        users = session.exec(select(User).order_by(User.created_at)).all()
        if not users:
            print("Пользователей нет. Заведите первого: python -m app.cli user add <логин>")
            return 0

        print(f"{'логин':<20} {'имя':<20} {'статус':<10} {'админ':<6} сессий")
        for user in users:
            live = session.exec(
                select(AuthSession).where(
                    AuthSession.user_id == user.id, AuthSession.expires_at > now
                )
            ).all()
            status = "активен" if user.is_active else "отключён"
            print(
                f"{user.username:<20} {user.display_name:<20} {status:<10} "
                f"{'да' if user.is_admin else '—':<6} {len(live)}"
            )
    return 0


def cmd_passwd(args: argparse.Namespace) -> int:
    with session_scope() as session:
        user = _find(session, args.username)
        if not user:
            print(f"Нет пользователя {args.username!r}.", file=sys.stderr)
            return 1

        user.password_hash = hash_password(_read_new_password())
        session.add(user)

        # A password change that leaves the old sessions alive does not lock
        # anybody out, which is usually the reason for changing it.
        dropped = revoke_all_for_user(session, user.id)

    print(f"Пароль обновлён, сессий завершено: {dropped}.")
    return 0


def cmd_disable(args: argparse.Namespace) -> int:
    with session_scope() as session:
        user = _find(session, args.username)
        if not user:
            print(f"Нет пользователя {args.username!r}.", file=sys.stderr)
            return 1

        user.is_active = False
        user.deactivated_at = datetime.utcnow()
        session.add(user)
        dropped = revoke_all_for_user(session, user.id)
        name = user.username

    print(f"Пользователь {name!r} отключён, сессий завершено: {dropped}.")
    print("История правок сохранена: его имя остаётся в updated_by у песен.")
    return 0


def cmd_enable(args: argparse.Namespace) -> int:
    with session_scope() as session:
        user = _find(session, args.username)
        if not user:
            print(f"Нет пользователя {args.username!r}.", file=sys.stderr)
            return 1
        user.is_active = True
        user.deactivated_at = None
        session.add(user)
        name = user.username

    print(f"Пользователь {name!r} снова активен. Войти нужно заново.")
    return 0


def cmd_logout(args: argparse.Namespace) -> int:
    with session_scope() as session:
        user = _find(session, args.username)
        if not user:
            print(f"Нет пользователя {args.username!r}.", file=sys.stderr)
            return 1
        dropped = revoke_all_for_user(session, user.id)

    print(f"Завершено сессий: {dropped}.")
    return 0


def cmd_delete(args: argparse.Namespace) -> int:
    """Remove the row outright.

    `disable` is almost always the right command instead: song history holds
    display names, and deleting the account is what makes "кто изменил" stop
    lining up with anybody. Kept for the case where the row must genuinely go.
    """

    with session_scope() as session:
        user = _find(session, args.username)
        if not user:
            print(f"Нет пользователя {args.username!r}.", file=sys.stderr)
            return 1

        if not args.force:
            print(f"Удаление {user.username!r} — операция без отката.")
            print("Обычно достаточно `user disable`: доступ пропадает, история остаётся.")
            if input("Введите логин ещё раз для подтверждения: ").strip() != user.username:
                print("Отменено.")
                return 1

        revoke_all_for_user(session, user.id)
        session.delete(user)

    print(f"Пользователь {args.username!r} удалён.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description=__doc__)
    sub = parser.add_subparsers(dest="group", required=True)

    user = sub.add_parser("user", help="управление пользователями").add_subparsers(
        dest="command", required=True
    )

    add = user.add_parser("add", help="завести пользователя")
    add.add_argument("username")
    add.add_argument("--display-name", help="имя в интерфейсе (по умолчанию — логин)")
    add.add_argument("--admin", action="store_true", help="пометить администратором")
    add.set_defaults(func=cmd_add)

    listing = user.add_parser("list", help="показать всех")
    listing.set_defaults(func=cmd_list)

    passwd = user.add_parser("passwd", help="сменить пароль и завершить все сессии")
    passwd.add_argument("username")
    passwd.set_defaults(func=cmd_passwd)

    disable = user.add_parser("disable", help="закрыть доступ, сохранив историю")
    disable.add_argument("username")
    disable.set_defaults(func=cmd_disable)

    enable = user.add_parser("enable", help="вернуть доступ")
    enable.add_argument("username")
    enable.set_defaults(func=cmd_enable)

    logout = user.add_parser("logout", help="завершить все сессии пользователя")
    logout.add_argument("username")
    logout.set_defaults(func=cmd_logout)

    delete = user.add_parser("delete", help="удалить строку пользователя насовсем")
    delete.add_argument("username")
    delete.add_argument("--force", action="store_true", help="без подтверждения")
    delete.set_defaults(func=cmd_delete)

    return parser


def _report_database() -> None:
    """Say which file is about to be edited, resolved to an absolute path.

    `DATABASE_URL` is relative by default (`sqlite:///./songs.db`), so running
    this from the wrong directory does not fail — it quietly creates a second,
    empty database and reports success. Printing the resolved path, and
    whether the file already existed, turns that into something visible before
    the mistake is made rather than a week later when nobody can sign in.
    """

    url = settings.database_url
    if not url.startswith("sqlite:"):
        print(f"База: {url}", file=sys.stderr)
        return

    path = Path(url.split("///", 1)[-1]).resolve()
    existed = path.exists()
    print(f"База: {path}", file=sys.stderr)
    if not existed:
        print(
            "  ВНИМАНИЕ: файла не было, создан новый и пустой.\n"
            "  Если пользователи должны были там быть — вы запустились не из той\n"
            "  директории. Перейдите туда, где лежит боевая songs.db, и повторите.",
            file=sys.stderr,
        )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    # Reported before the tables are created, so "the file was missing" is
    # still true information rather than something this call just changed.
    _report_database()
    # The server may never have started against this file yet — creating the
    # first user has to work on an empty database.
    init_database()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
