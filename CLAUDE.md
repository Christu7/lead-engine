# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

LeadEngine — a FastAPI backend service with PostgreSQL and Redis, running in Docker.

## Commands

```bash
# Start all services (backend at localhost:8000, docs at localhost:8000/docs)
docker-compose up --build

# Run in background
docker-compose up -d --build

# Stop services
docker-compose down

# View backend logs
docker-compose logs -f backend
```

## Architecture

- **app/main.py** — FastAPI app entrypoint, mounts routers
- **app/api/** — Route handlers (routers). Each file defines an `APIRouter`, included in main with a prefix.
- **app/models/** — SQLAlchemy ORM models using `DeclarativeBase` from `app/core/database.py`
- **app/services/** — Business logic layer, called by route handlers
- **app/core/config.py** — `Settings` via pydantic-settings, loaded from `.env`
- **app/core/database.py** — Async SQLAlchemy engine, session factory, `Base` class, `get_db` dependency
- **app/core/redis.py** — Async Redis client instance

## Key Conventions

- All database access is async (`asyncpg` + `AsyncSession`)
- Config is read from environment variables (see `.env.example`)
- Routers are mounted in `app/main.py` under `/api` prefix
- Docker Compose service names (`db`, `redis`) are used as hostnames in connection URLs
