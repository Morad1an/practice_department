from __future__ import annotations

import argparse
import asyncio
from getpass import getpass

from src.app.database import async_session_maker
from src.app.services.auth import upsert_auth_user


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create or update application user credentials.",
    )
    parser.add_argument("--username", required=True, help="Login name")
    parser.add_argument(
        "--role",
        required=True,
        choices=["viewer", "editor"],
        help="Access role",
    )
    parser.add_argument(
        "--password",
        help="Password. If omitted, the script will ask securely.",
    )
    parser.add_argument(
        "--inactive",
        action="store_true",
        help="Create/update the user as inactive.",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    password = args.password or getpass("Password: ")

    async with async_session_maker() as session:
        user = await upsert_auth_user(
            session,
            username=args.username,
            password=password,
            role=args.role,
            is_active=not args.inactive,
        )

    print(
        f"User '{user.username}' saved with role '{user.role}'"
        + ("" if user.is_active else " (inactive)")
    )


if __name__ == "__main__":
    asyncio.run(main())
