import asyncio
import logging
import time
import uuid

from aiogram import Bot
from aiogram.types import BufferedInputFile
from celery import Task
from redis import Redis

from link_checker.celery_app import celery_app
from link_checker.checker import LinkChecker
from link_checker.config import get_settings
from link_checker.jobs import SyncJobStore
from link_checker.models import LinkState
from link_checker.parser import InputUrl
from link_checker.reporting import build_csv, summarize_ru

logger = logging.getLogger(__name__)

_RETRYABLE_STATES = {LinkState.BROKEN, LinkState.TIMEOUT, LinkState.NETWORK_ERROR}


async def _send_report(
    *, chat_id: int, job_id: str, results_count: int, report: bytes, caption: str
) -> int:
    settings = get_settings()
    bot = Bot(token=settings.bot_token.get_secret_value())
    try:
        message = await bot.send_document(
            chat_id=chat_id,
            document=BufferedInputFile(
                report,
                filename=f"otchet-ssylki-{job_id}-{results_count}.csv",
            ),
            caption=caption,
        )
        return message.message_id
    finally:
        await bot.session.close()


async def _send_text(chat_id: int, text: str) -> None:
    settings = get_settings()
    bot = Bot(token=settings.bot_token.get_secret_value())
    try:
        await bot.send_message(chat_id=chat_id, text=text)
    finally:
        await bot.session.close()


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
                f"Задание {job_id}: ссылок для повторной проверки больше нет.",
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
    previous_pending = len(urls)
    recovered = sum(result.is_working for result in results)
    previous_working = int(job.get("working", "0"))
    total = int(job["total"])
    working = recovered if initial else previous_working + recovered
    failed = total - working
    report_message_id: int | None = None

    if initial:
        report_message_id = await _send_report(
            chat_id=chat_id,
            job_id=job_id,
            results_count=len(results),
            report=build_csv(results),
            caption=(
                f"Первичная проверка задания {job_id} завершена.\n"
                f"{summarize_ru(results)}\n"
                f"На повторный контроль поставлено: {len(retry_urls):,}."
            ),
        )
    elif len(retry_urls) < previous_pending:
        report_message_id = await _send_report(
            chat_id=chat_id,
            job_id=job_id,
            results_count=len(results),
            report=build_csv(results),
            caption=(
                f"Повторная проверка задания {job_id}.\n"
                f"Восстановились или больше не требуют повторов: "
                f"{previous_pending - len(retry_urls):,}.\n"
                f"Остаются на контроле: {len(retry_urls):,}."
            ),
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
    if report_message_id is not None:
        values["report_message_id"] = report_message_id
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
            interval = int(job.get("interval_seconds", settings.recheck_interval_seconds))
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
