import asyncio
import logging
import time
import uuid
from collections.abc import Sequence

from aiogram import Bot
from celery import Task
from redis import Redis

from link_checker.celery_app import celery_app
from link_checker.checker import LinkChecker
from link_checker.config import get_settings
from link_checker.jobs import SyncJobStore
from link_checker.models import LinkResult, LinkState
from link_checker.parser import InputUrl
from link_checker.telegram_links import extract_public_username

logger = logging.getLogger(__name__)

_RETRYABLE_STATES = {LinkState.BROKEN, LinkState.TIMEOUT, LinkState.NETWORK_ERROR}


async def _send_text(chat_id: int, text: str) -> None:
    settings = get_settings()
    bot = Bot(token=settings.bot_token.get_secret_value())
    try:
        await bot.send_message(chat_id=chat_id, text=text)
    finally:
        await bot.session.close()


def _summary(results: Sequence[LinkResult]) -> str:
    found = sum(result.is_working for result in results)
    missing = sum(result.state is LinkState.BROKEN for result in results)
    temporary = sum(
        result.state in {LinkState.TIMEOUT, LinkState.NETWORK_ERROR} for result in results
    )
    invalid = sum(result.state is LinkState.INVALID for result in results)
    return (
        f"Проверено: {len(results):,}; найдено: {found:,}; "
        f"username не найдены: {missing:,}; "
        f"временные ошибки: {temporary:,}; неподдерживаемые ссылки: {invalid:,}."
    )


def _missing_username_messages(results: Sequence[LinkResult]) -> list[str]:
    usernames: list[str] = []
    seen: set[str] = set()
    for result in results:
        if result.state is not LinkState.BROKEN:
            continue
        try:
            username = f"@{extract_public_username(result.url)}"
        except ValueError:
            username = result.url
        if username not in seen:
            seen.add(username)
            usernames.append(username)

    if not usernames:
        return []

    messages: list[str] = []
    current = "Username не найдены:\n"
    for username in usernames:
        line = f"• {username}\n"
        if len(current) + len(line) > 4_000:
            messages.append(current.rstrip())
            current = "Username не найдены (продолжение):\n"
        current += line
    messages.append(current.rstrip())
    return messages


async def _send_check_result(
    *,
    chat_id: int,
    job_id: str,
    results: Sequence[LinkResult],
    initial: bool,
    retry_count: int,
) -> None:
    title = (
        f"Первичная проверка t.me-ссылок завершена. Задание: {job_id}."
        if initial
        else f"Повторная проверка t.me-ссылок завершена. Задание: {job_id}."
    )
    await _send_text(
        chat_id,
        f"{title}\n{_summary(results)}\nНа повторной проверке: {retry_count:,}.",
    )
    for message in _missing_username_messages(results):
        await _send_text(chat_id, message)


async def _check_cycle(
    job_id: str,
    generation: int,
    store: SyncJobStore,
    chat_id: int,
) -> tuple[int, int]:
    settings = get_settings()
    job = store.get(job_id)
    cycle = int(job.get("cycle", "0"))
    initial = cycle == 0
    urls = store.get_urls(job_id) if initial else store.get_retry_urls(job_id)

    if not urls:
        if store.is_current(job_id, generation):
            store.update(job_id, status="completed", monitoring=0, pending=0)
            store.unschedule(job_id)
            await _send_text(
                chat_id,
                f"Задание {job_id}: username для повторной проверки больше нет.",
            )
        return 0, 0

    results = await LinkChecker(settings).check_all(urls)
    if not store.is_current(job_id, generation):
        logger.info("Отбрасываем устаревший результат задания %s", job_id)
        return len(results), 0

    retry_urls = [
        InputUrl(result.line_number, result.url)
        for result in results
        if not result.is_working and result.state in _RETRYABLE_STATES
    ]
    recovered = sum(result.is_working for result in results)
    previous_working = int(job.get("working", "0"))
    total = int(job["total"])
    working = recovered if initial else previous_working + recovered
    failed = total - working
    await _send_check_result(
        chat_id=chat_id,
        job_id=job_id,
        results=results,
        initial=initial,
        retry_count=len(retry_urls),
    )

    if not store.is_current(job_id, generation):
        return len(results), recovered

    store.set_retry_urls(job_id, retry_urls)
    values: dict[str, object] = {
        "status": "monitoring" if retry_urls else "completed",
        "monitoring": 1 if retry_urls else 0,
        "cycle": cycle + 1,
        "pending": len(retry_urls),
        "working": working,
        "failed": failed,
        "error": "",
        "last_check_at": time.time(),
    }
    store.update(job_id, **values)

    if not retry_urls:
        store.unschedule(job_id)
    return len(results), recovered


@celery_app.task(
    bind=True,
    base=Task,
    name="link_checker.check_job",
    ignore_result=False,
)  # type: ignore[untyped-decorator]
def check_job(self: Task, job_id: str, generation: int) -> dict[str, int | str]:
    settings = get_settings()
    redis = Redis.from_url(settings.redis_job_url, decode_responses=True)
    store = SyncJobStore(redis, settings.job_ttl_seconds)
    token = str(self.request.id or uuid.uuid4().hex)
    locked = False
    try:
        job = store.get(job_id)
        if not job:
            return {"job_id": job_id, "status": "expired"}
        if not store.is_current(job_id, generation):
            return {"job_id": job_id, "status": "stale"}
        locked = store.acquire_check_lock(
            job_id, token, settings.monitor_lock_timeout_seconds
        )
        if not locked:
            return {"job_id": job_id, "status": "already_running"}

        chat_id = int(job["chat_id"])
        store.update(job_id, status="running", celery_task_id=self.request.id)
        checked, recovered = asyncio.run(
            _check_cycle(job_id, generation, store, chat_id)
        )
        return {"job_id": job_id, "checked": checked, "recovered": recovered}
    except Exception as exc:
        logger.exception("Ошибка задания %s", job_id)
        if store.is_current(job_id, generation):
            store.update(
                job_id,
                status="retry_wait",
                error=f"{type(exc).__name__}: {exc}"[:500],
            )
        raise
    finally:
        if locked:
            store.release_check_lock(job_id, token)
        redis.close()


@celery_app.task(
    name="link_checker.dispatch_due_jobs",
    ignore_result=True,
)  # type: ignore[untyped-decorator]
def dispatch_due_jobs() -> dict[str, int]:
    settings = get_settings()
    redis = Redis.from_url(settings.redis_job_url, decode_responses=True)
    store = SyncJobStore(redis, settings.job_ttl_seconds)
    dispatched = 0
    try:
        for job_id in store.due_job_ids(time.time()):
            job = store.get(job_id)
            if not job or job.get("monitoring") != "1":
                store.unschedule(job_id)
                continue
            # The monitoring cadence is global; apply configuration changes to active jobs too.
            interval = settings.recheck_interval_seconds
            generation = int(job["generation"])
            store.schedule_next(job_id, interval)
            check_job.apply_async(
                args=[job_id, generation],
                task_id=(
                    f"link-monitor-{job_id}-{generation}-{uuid.uuid4().hex[:8]}"
                ),
            )
            dispatched += 1
        return {"dispatched": dispatched}
    finally:
        redis.close()
