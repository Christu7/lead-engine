"""
Idempotent seed script — creates the default admin user and default client.

Usage (stack must be running):
    docker compose exec backend python seed.py

Reads from environment variables:
    ADMIN_EMAIL       (default: admin@leadengine.local)
    ADMIN_PASSWORD    (default: changeme)
    DEFAULT_CLIENT_NAME  (default: Default)
"""

import asyncio

from sqlalchemy import select

from app.core.config import settings
from app.core.database import async_session as AsyncSessionLocal
from app.core.security import hash_password
from app.models.client import Client
from app.models.user import User, UserClient


async def seed() -> None:
    async with AsyncSessionLocal() as db:
        # 1. Ensure default client exists
        result = await db.execute(select(Client).where(Client.name == settings.DEFAULT_CLIENT_NAME))
        client = result.scalar_one_or_none()
        if client is None:
            client = Client(name=settings.DEFAULT_CLIENT_NAME)
            db.add(client)
            await db.flush()
            print(f"Created client: {settings.DEFAULT_CLIENT_NAME} (id={client.id})")
        else:
            print(f"Client already exists: {settings.DEFAULT_CLIENT_NAME} (id={client.id})")

        # 2. Ensure admin user exists with correct role
        result = await db.execute(select(User).where(User.email == settings.ADMIN_EMAIL))
        user = result.scalar_one_or_none()
        if user is None:
            user = User(
                email=settings.ADMIN_EMAIL,
                hashed_password=hash_password(settings.ADMIN_PASSWORD),
                role="superadmin",
                is_active=True,
            )
            db.add(user)
            await db.flush()
            print(f"Created superadmin user: {settings.ADMIN_EMAIL} (id={user.id})")
        else:
            # Always ensure role=superadmin and is_active=True even if the user was
            # pre-created with a different role (e.g. via the API with role=member).
            # Without this, seed.py is not idempotent and leaves the admin broken.
            if user.role != "superadmin" or not user.is_active:
                user.role = "superadmin"
                user.is_active = True
                print(f"Updated admin user to superadmin: {settings.ADMIN_EMAIL} (id={user.id})")
            else:
                print(f"Superadmin user already exists: {settings.ADMIN_EMAIL} (id={user.id})")

        # 3. Ensure admin is assigned to default client
        result = await db.execute(
            select(UserClient).where(
                UserClient.user_id == user.id,
                UserClient.client_id == client.id,
            )
        )
        if result.scalar_one_or_none() is None:
            db.add(UserClient(user_id=user.id, client_id=client.id))
            print(f"Assigned {settings.ADMIN_EMAIL} to client {settings.DEFAULT_CLIENT_NAME}")
        else:
            print(f"Assignment already exists")

        await db.commit()
        print("Seed complete.")


if __name__ == "__main__":
    asyncio.run(seed())
