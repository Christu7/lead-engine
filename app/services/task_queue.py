"""Sorted-set based task queue with scheduled delivery and crash recovery.

Tasks are stored in a Redis sorted set (score = scheduled Unix timestamp).
A task with score <= now is ready to process. Tasks scheduled in the future
(rate-limit backoff, delayed retry) have score > now.

Processing safety: dequeued tasks are moved atomically to a processing set.
On worker restart, stranded tasks in the processing set are recovered.
"""
import json
import logging
import time

from app.core.redis import redis

logger = logging.getLogger(__name__)

TASK_QUEUE_KEY = "task_queue"
TASK_PROCESSING_KEY = "task_queue:processing"

# Retry delays in seconds for rate-limited (429) errors
RATE_LIMIT_DELAYS = [60, 300, 600]
# Retry delays in seconds for transient (5xx / network) errors
TRANSIENT_DELAYS = [30, 120, 300]
# Maximum retries before dead-lettering
MAX_TASK_RETRIES = 3

# Atomically pop the next ready task and record it in the processing set.
# KEYS[1] = queue sorted set, KEYS[2] = processing sorted set
# ARGV[1] = current Unix timestamp as string
_DEQUEUE_LUA = """
local items = redis.call('ZRANGEBYSCORE', KEYS[1], '-inf', ARGV[1], 'LIMIT', 0, 1)
if #items == 0 then return nil end
local item = items[1]
redis.call('ZREM', KEYS[1], item)
redis.call('ZADD', KEYS[2], ARGV[1], item)
return item
"""


async def enqueue(task_type: str, payload: dict, delay_seconds: float = 0) -> None:
    """Add a task to the queue, optionally scheduled for the future."""
    score = time.time() + delay_seconds
    data = json.dumps({"task_type": task_type, "payload": payload})
    await redis.zadd(TASK_QUEUE_KEY, {data: score})


async def dequeue() -> tuple[str, dict] | None:
    """Atomically dequeue the next ready task.

    Returns (raw_string, task_dict) or None if no task is ready.
    The raw string must be passed to ack() or nack_*() after processing.
    """
    now = time.time()
    raw = await redis.eval(
        _DEQUEUE_LUA,
        2,
        TASK_QUEUE_KEY,
        TASK_PROCESSING_KEY,
        str(now),
    )
    if raw is None:
        return None
    return raw, json.loads(raw)


async def ack(raw: str) -> None:
    """Remove a successfully processed (or permanently failed) task from the processing set."""
    await redis.zrem(TASK_PROCESSING_KEY, raw)


async def nack_rate_limited(raw: str, delay_seconds: float, new_retry_count: int) -> None:
    """Return a rate-limited task to the queue with an incremented retry count and future score."""
    try:
        data = json.loads(raw)
        data["payload"]["retry_count"] = new_retry_count
        new_raw = json.dumps(data)
    except Exception:
        new_raw = raw

    score = time.time() + delay_seconds
    async with redis.pipeline() as pipe:
        pipe.zrem(TASK_PROCESSING_KEY, raw)
        pipe.zadd(TASK_QUEUE_KEY, {new_raw: score})
        await pipe.execute()


async def nack_transient(raw: str, delay_seconds: float, new_retry_count: int) -> None:
    """Return a transiently-failed task to the queue with backoff."""
    await nack_rate_limited(raw, delay_seconds, new_retry_count)


_RECOVER_LOCK_KEY = "task_queue:recover_lock"
_RECOVER_LOCK_TTL = 30  # seconds


async def recover_stranded() -> int:
    """On startup, re-enqueue any tasks stranded in the processing set.

    Handles the case where the worker crashed while processing a task.
    Uses a Redis SETNX lock so only one worker runs recovery at a time
    (prevents double-enqueuing when multiple workers restart simultaneously).
    """
    acquired = await redis.set(_RECOVER_LOCK_KEY, "1", nx=True, ex=_RECOVER_LOCK_TTL)
    if not acquired:
        logger.info("recover_stranded: lock held by another worker, skipping")
        return 0

    try:
        stranded = await redis.zrangebyscore(TASK_PROCESSING_KEY, "-inf", "+inf")
        if not stranded:
            return 0

        now = time.time()
        recovered = 0
        dead_lettered = 0

        for item in stranded:
            retry_count = 0
            client_id = 0
            payload_for_dl: dict = {}
            try:
                data = json.loads(item)
                payload_for_dl = data.get("payload", {})
                retry_count = payload_for_dl.get("retry_count", 0)
                client_id = payload_for_dl.get("client_id", 0)
            except Exception:
                pass

            await redis.zrem(TASK_PROCESSING_KEY, item)

            if retry_count >= MAX_TASK_RETRIES:
                # Task has already exhausted its retry budget — dead letter it.
                dead_lettered += 1
                logger.warning(
                    "recover_stranded: task exhausted retries (count=%d) — dead lettering: %s",
                    retry_count,
                    item[:120],
                )
                try:
                    from app.services.dead_letter import DeadLetterService, DeadLetterType
                    dl_svc = DeadLetterService(redis)
                    await dl_svc.push(
                        DeadLetterType.ENRICHMENT,
                        lead_id=payload_for_dl.get("lead_id", 0),
                        client_id=client_id,
                        error=f"Stranded task exceeded max retries ({MAX_TASK_RETRIES}): {item[:200]}",
                    )
                except Exception as dl_exc:
                    logger.error("recover_stranded: failed to write dead letter: %s", dl_exc)
            else:
                await redis.zadd(TASK_QUEUE_KEY, {item: now})
                recovered += 1

        logger.info(
            "recover_stranded: re-enqueued %d, dead-lettered %d stranded tasks",
            recovered,
            dead_lettered,
        )
        return recovered + dead_lettered
    finally:
        await redis.delete(_RECOVER_LOCK_KEY)


async def migrate_legacy_list_queue() -> int:
    """One-time migration: move items from the old enrichment_queue LIST into task_queue.

    Safe to call on every worker startup — does nothing once the list is empty.
    """
    from app.services.enrichment.queue import QUEUE_KEY as LEGACY_KEY

    migrated = 0
    now = time.time()
    while True:
        raw = await redis.rpop(LEGACY_KEY)
        if raw is None:
            break
        try:
            old_payload = json.loads(raw)
            new_data = json.dumps({"task_type": "lead_enrichment", "payload": old_payload})
            await redis.zadd(TASK_QUEUE_KEY, {new_data: now})
            migrated += 1
        except Exception as exc:
            logger.warning("migrate_legacy_list_queue: skipping malformed item: %s", exc)
    return migrated


async def stats() -> dict:
    """Return current queue stats: counts by state and per-type breakdown."""
    now = time.time()

    total_queued = await redis.zcard(TASK_QUEUE_KEY)
    pending = await redis.zcount(TASK_QUEUE_KEY, "-inf", now)
    scheduled = total_queued - pending
    processing = await redis.zcard(TASK_PROCESSING_KEY)

    all_items_with_scores = await redis.zrangebyscore(
        TASK_QUEUE_KEY, "-inf", "+inf", withscores=True
    )
    tasks_by_type: dict[str, int] = {}
    rate_limited_until: float | None = None

    for raw, score in all_items_with_scores:
        try:
            data = json.loads(raw)
            t = data.get("task_type", "unknown")
            tasks_by_type[t] = tasks_by_type.get(t, 0) + 1
        except Exception:
            pass
        if score > now and rate_limited_until is None:
            rate_limited_until = score

    return {
        "pending": pending,
        "scheduled": scheduled,
        "processing": processing,
        "tasks_by_type": tasks_by_type,
        "rate_limited_until": rate_limited_until,
    }
