import json
import logging
import time
import uuid
from enum import Enum
from typing import Any

from app.core.exceptions import DeadLetterError

logger = logging.getLogger(__name__)

DL_INDEX_KEY = "dead_letter:index"
DL_ENTRY_PREFIX = "dead_letter:"
DL_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 days


class DeadLetterType(str, Enum):
    ENRICHMENT = "enrichment"
    ROUTING = "routing"
    AI_ANALYSIS = "ai_analysis"


class DeadLetterService:
    def __init__(self, redis_client) -> None:
        self._redis = redis_client

    async def push(
        self,
        dl_type: DeadLetterType,
        lead_id: int,
        client_id: int,
        error: str,
        extra: dict[str, Any] | None = None,
    ) -> str:
        """Write a new dead letter entry. Returns the entry_id."""
        entry_id = str(uuid.uuid4())
        now = time.time()
        entry = {
            "id": entry_id,
            "type": dl_type.value,
            "lead_id": lead_id,
            "client_id": client_id,
            "error": error,
            "created_at": now,
            "extra": extra or {},
        }
        key = f"{DL_ENTRY_PREFIX}{entry_id}"
        try:
            await self._redis.setex(key, DL_TTL_SECONDS, json.dumps(entry))
            await self._redis.zadd(DL_INDEX_KEY, {entry_id: now})
            logger.info(
                "Dead letter written",
                extra={"entry_id": entry_id, "type": dl_type.value, "lead_id": lead_id},
            )
        except Exception as exc:
            raise DeadLetterError(f"Failed to write dead letter entry: {exc}") from exc
        return entry_id

    async def list(self, limit: int = 100, client_ids: list[int] | None = None) -> list[dict]:
        """Return up to `limit` dead letter entries, newest first.

        If `client_ids` is provided, only entries whose client_id is in that
        list are returned.  Pass None to return all entries (superadmin use).
        """
        try:
            entry_ids = await self._redis.zrevrange(DL_INDEX_KEY, 0, limit - 1)
        except Exception as exc:
            raise DeadLetterError(f"Failed to list dead letters: {exc}") from exc

        entries = []
        for eid in entry_ids:
            raw = await self._redis.get(f"{DL_ENTRY_PREFIX}{eid}")
            if raw:
                try:
                    entry = json.loads(raw)
                except json.JSONDecodeError:
                    logger.warning(
                        "Dead letter entry %s has invalid JSON — skipping", eid
                    )
                    continue
                if client_ids is None or entry.get("client_id") in client_ids:
                    entries.append(entry)
            else:
                # Entry has expired (TTL elapsed) but the index still holds its ID.
                # Clean up the orphaned reference so the index stays accurate.
                try:
                    await self._redis.zrem(DL_INDEX_KEY, eid)
                    logger.debug("Dead letter index: removed expired entry %s", eid)
                except Exception:
                    pass
        return entries

    async def get(self, entry_id: str) -> dict | None:
        """Fetch a single dead letter entry by ID."""
        raw = await self._redis.get(f"{DL_ENTRY_PREFIX}{entry_id}")
        if raw is None:
            return None
        return json.loads(raw)

    async def dismiss(self, entry_id: str) -> bool:
        """Remove an entry from the index and delete its key. Returns True if found."""
        removed = await self._redis.zrem(DL_INDEX_KEY, entry_id)
        await self._redis.delete(f"{DL_ENTRY_PREFIX}{entry_id}")
        return removed > 0
