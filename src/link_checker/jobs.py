import json
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import cast

from redis import Redis
from redis.asyncio import Redis as AsyncRedis

from link_checker.parser import InputUrl

_DUE_JOBS_KEY = "link-checker:monitor:due"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _job_key(job_id: str) -> str:
    return f"link-checker:job:{job_id}"


def _urls_key(job_id: str) -> str:
    return f"link-checker:job:{job_id}:urls"


def _retry_urls_key(job_id: str) -> str:
    return f"link-checker:job:{job_id}:retry-urls"


def _chat_database_key(chat_id: int) -> str:
    return f"link-checker:chat:{chat_id}:database"


def _check_lock_key(job_id: str) -> str:
    return f"link-checker:job:{job_id}:check-lock"


_RELEASE_LOCK_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""


async def create_job(
    redis: AsyncRedis,
    *,
    job_id: str,
    chat_id: int,
    urls: Sequence[InputUrl],
    ttl_seconds: int,
    interval_seconds: int,
) -> None:
    payloads = [json.dumps({"line": item.line_number, "url": item.url}) for item in urls]
    async with redis.pipeline(transaction=True) as pipe:
        pipe.hset(
            _job_key(job_id),
            mapping={
                "status": "ready",
                "monitoring": "0",
                "generation": "0",
                "cycle": "0",
                "chat_id": str(chat_id),
                "total": str(len(urls)),
                "pending": str(len(urls)),
                "interval_seconds": str(interval_seconds),
                "created_at": _now(),
                "updated_at": _now(),
            },
        )
        pipe.rpush(_urls_key(job_id), *payloads)
        pipe.set(_chat_database_key(chat_id), job_id, ex=ttl_seconds)
        pipe.expire(_job_key(job_id), ttl_seconds)
        pipe.expire(_urls_key(job_id), ttl_seconds)
        await pipe.execute()


async def get_job(redis: AsyncRedis, job_id: str) -> dict[str, str] | None:
    data = await redis.hgetall(_job_key(job_id))  # type: ignore[misc]
    return data or None


async def get_chat_job(
    redis: AsyncRedis, chat_id: int
) -> tuple[str, dict[str, str]] | None:
    job_id = await redis.get(_chat_database_key(chat_id))
    if not job_id:
        return None
    job = await get_job(redis, str(job_id))
    if job is None:
        await redis.delete(_chat_database_key(chat_id))
        return None
    return str(job_id), job


async def start_monitoring(
    redis: AsyncRedis,
    *,
    job_id: str,
    chat_id: int,
    ttl_seconds: int,
    interval_seconds: int,
    restart: bool,
) -> int:
    generation = int(
        await redis.hincrby(_job_key(job_id), "generation", 1)  # type: ignore[misc]
    )
    mapping = {
        "status": "queued",
        "monitoring": "1",
        "generation": str(generation),
        "interval_seconds": str(interval_seconds),
        "next_run_at": str(time.time() + interval_seconds),
        "updated_at": _now(),
    }
    if restart:
        mapping.update({"cycle": "0", "pending": "0", "working": "0", "failed": "0"})

    async with redis.pipeline(transaction=True) as pipe:
        pipe.hset(_job_key(job_id), mapping=mapping)
        if restart:
            pipe.delete(_retry_urls_key(job_id))
        pipe.set(_chat_database_key(chat_id), job_id, ex=ttl_seconds)
        pipe.zadd(_DUE_JOBS_KEY, {job_id: time.time() + interval_seconds})
        pipe.expire(_job_key(job_id), ttl_seconds)
        pipe.expire(_urls_key(job_id), ttl_seconds)
        await pipe.execute()
    return generation


async def stop_monitoring(redis: AsyncRedis, *, job_id: str, ttl_seconds: int) -> None:
    await redis.hincrby(_job_key(job_id), "generation", 1)  # type: ignore[misc]
    async with redis.pipeline(transaction=True) as pipe:
        pipe.hset(
            _job_key(job_id),
            mapping={"status": "stopped", "monitoring": "0", "updated_at": _now()},
        )
        pipe.zrem(_DUE_JOBS_KEY, job_id)
        pipe.expire(_job_key(job_id), ttl_seconds)
        pipe.expire(_urls_key(job_id), ttl_seconds)
        pipe.expire(_retry_urls_key(job_id), ttl_seconds)
        await pipe.execute()


class SyncJobStore:
    def __init__(self, redis: Redis, ttl_seconds: int) -> None:
        self.redis = redis
        self.ttl_seconds = ttl_seconds

    def get_urls(self, job_id: str) -> list[InputUrl]:
        return self._read_urls(_urls_key(job_id))

    def get_retry_urls(self, job_id: str) -> list[InputUrl]:
        return self._read_urls(_retry_urls_key(job_id))

    def _read_urls(self, key: str) -> list[InputUrl]:
        values = cast(list[str], self.redis.lrange(key, 0, -1))
        return [
            InputUrl(line_number=(item := json.loads(value))["line"], url=item["url"])
            for value in values
        ]

    def set_retry_urls(self, job_id: str, urls: Sequence[InputUrl]) -> None:
        payloads = [json.dumps({"line": item.line_number, "url": item.url}) for item in urls]
        key = _retry_urls_key(job_id)
        with self.redis.pipeline(transaction=True) as pipe:
            pipe.delete(key)
            if payloads:
                pipe.rpush(key, *payloads)
                pipe.expire(key, self.ttl_seconds)
            pipe.execute()

    def get(self, job_id: str) -> dict[str, str]:
        return cast(dict[str, str], self.redis.hgetall(_job_key(job_id)))

    def update(self, job_id: str, **values: object) -> None:
        mapping = {key: str(value) for key, value in values.items()}
        mapping["updated_at"] = _now()
        key = _job_key(job_id)
        chat_id = cast(str | None, self.redis.hget(key, "chat_id"))
        with self.redis.pipeline(transaction=True) as pipe:
            pipe.hset(key, mapping=mapping)
            pipe.expire(key, self.ttl_seconds)
            pipe.expire(_urls_key(job_id), self.ttl_seconds)
            pipe.expire(_retry_urls_key(job_id), self.ttl_seconds)
            if chat_id is not None:
                pipe.expire(_chat_database_key(int(chat_id)), self.ttl_seconds)
            pipe.execute()

    def is_current(self, job_id: str, generation: int) -> bool:
        job = self.get(job_id)
        return job.get("monitoring") == "1" and int(job.get("generation", "-1")) == generation

    def acquire_check_lock(self, job_id: str, token: str, timeout_seconds: int) -> bool:
        return bool(
            self.redis.set(_check_lock_key(job_id), token, ex=timeout_seconds, nx=True)
        )

    def release_check_lock(self, job_id: str, token: str) -> None:
        self.redis.eval(_RELEASE_LOCK_SCRIPT, 1, _check_lock_key(job_id), token)

    def schedule_next(self, job_id: str, interval_seconds: int) -> None:
        next_run = time.time() + interval_seconds
        with self.redis.pipeline(transaction=True) as pipe:
            pipe.zadd(_DUE_JOBS_KEY, {job_id: next_run})
            pipe.hset(
                _job_key(job_id),
                mapping={"next_run_at": str(next_run), "updated_at": _now()},
            )
            pipe.execute()

    def unschedule(self, job_id: str) -> None:
        self.redis.zrem(_DUE_JOBS_KEY, job_id)

    def due_job_ids(self, now: float, limit: int = 100) -> list[str]:
        return cast(
            list[str],
            self.redis.zrangebyscore(_DUE_JOBS_KEY, "-inf", now, start=0, num=limit),
        )
