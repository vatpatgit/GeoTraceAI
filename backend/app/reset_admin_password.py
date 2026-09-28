"""One-off script to create or reset the default admin password hash."""
import asyncio
import sys
from pathlib import Path

# Add backend directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.auth.password import hash_password, verify_password
from app.database import async_session_maker
from app.models import User

ADMIN_EMAIL = "admin@terratrack.dev"
ADMIN_PASSWORD = "admin123"
ADMIN_NAME = "Administrator"


async def main() -> None:
    password_hash = hash_password(ADMIN_PASSWORD)
    async with async_session_maker() as db:
        result = await db.execute(select(User).where(User.email == ADMIN_EMAIL))
        user = result.scalar_one_or_none()

        if user is None:
            user = User(
                email=ADMIN_EMAIL,
                name=ADMIN_NAME,
                role="admin",
                password_hash=password_hash,
                is_active=True,
            )
            db.add(user)
            action = "Created"
        else:
            user.password_hash = password_hash
            action = "Updated"

        await db.commit()
        await db.refresh(user)

        assert verify_password(ADMIN_PASSWORD, user.password_hash)
        print(f"[{action}] Admin user ready!")
        print(f"Email:    {ADMIN_EMAIL}")
        print(f"Password: {ADMIN_PASSWORD}")


if __name__ == "__main__":
    asyncio.run(main())