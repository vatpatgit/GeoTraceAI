"""One-off script to reset the default admin password hash."""
import asyncio

from sqlalchemy import select, update

from app.auth.password import hash_password, verify_password
from app.database import async_session_maker
from app.models import User

ADMIN_EMAIL = "admin@terratrack.dev"
ADMIN_PASSWORD = "admin123"


async def main() -> None:
    password_hash = hash_password(ADMIN_PASSWORD)
    async with async_session_maker() as db:
        await db.execute(
            update(User)
            .where(User.email == ADMIN_EMAIL)
            .values(password_hash=password_hash)
        )
        await db.commit()

        result = await db.execute(select(User).where(User.email == ADMIN_EMAIL))
        user = result.scalar_one()
        assert verify_password(ADMIN_PASSWORD, user.password_hash)
        print(f"Updated password for {ADMIN_EMAIL}")


if __name__ == "__main__":
    asyncio.run(main())
