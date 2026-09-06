import asyncio
import logging
import uuid

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from redis.asyncio import Redis

from link_checker.config import Settings, get_settings
from link_checker.jobs import (
    create_job,
    get_chat_job,
    get_job,
    start_monitoring,
    stop_monitoring,
)
from link_checker.parser import InputError, parse_url_file
from link_checker.tasks import check_job
from link_checker.ui import RESTART, START_SEARCH, STOP, UPLOAD_DATABASE, main_keyboard

router = Router()
logger = logging.getLogger(__name__)

_STATUS_RU = {
    "ready": "база загружена",
    "queued": "проверка поставлена в очередь",
    "running": "идёт проверка",
    "monitoring": "мониторинг активен",
    "stopped": "мониторинг остановлен",
    "completed": "все повторно проверяемые ссылки доступны",
    "retry_wait": "ожидание следующей попытки",
    "failed": "ошибка проверки",
    "failed_to_queue": "ошибка постановки в очередь",
}


def _format_interval(seconds: int) -> str:
    if seconds % 3600 == 0:
        return f"{seconds // 3600} ч."
    if seconds % 60 == 0:
        return f"{seconds // 60} мин."
    return f"{seconds} сек."


@router.message(CommandStart())
async def command_start(message: Message) -> None:
    await message.answer(
        "Бот проверяет ссылки из TXT-файла и круглосуточно перепроверяет "
        "недоступные адреса. Сначала загрузите базу, затем запустите поиск.",
        reply_markup=main_keyboard(),
    )


@router.message(Command("status"))
async def status(message: Message, redis: Redis) -> None:
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) == 2:
        job_id = parts[1].strip()
        job = await get_job(redis, job_id)
        if job is None or str(message.chat.id) != job.get("chat_id"):
            await message.answer("Задание не найдено или срок его хранения истёк.")
            return
    else:
        current = await get_chat_job(redis, message.chat.id)
        if current is None:
            await message.answer("База ещё не загружена.", reply_markup=main_keyboard())
            return
        job_id, job = current

    status_name = _STATUS_RU.get(job.get("status", ""), job.get("status", "неизвестно"))
    interval = _format_interval(int(job.get("interval_seconds", "1800")))
    response = (
        f"Задание {job_id}: {status_name}.\n"
        f"Всего ссылок: {job.get('total', '?')}; "
        f"ожидают перепроверки: {job.get('pending', '0')}.\n"
        f"Интервал: {interval}; циклов выполнено: {job.get('cycle', '0')}."
    )
    if job.get("error"):
        response += f"\nПоследняя ошибка: {job['error']}"
    await message.answer(response, reply_markup=main_keyboard())


@router.message(F.text == UPLOAD_DATABASE)
async def upload_database_prompt(message: Message) -> None:
    await message.answer(
        "Отправьте TXT-файл в кодировке UTF-8: одна ссылка http:// или https:// на строку.",
        reply_markup=main_keyboard(),
    )


async def _launch_monitoring(
    message: Message,
    settings: Settings,
    redis: Redis,
    *,
    restart: bool,
) -> None:
    current = await get_chat_job(redis, message.chat.id)
    if current is None:
        await message.answer("Сначала загрузите базу ссылок.", reply_markup=main_keyboard())
        return
    job_id, job = current
    if job.get("monitoring") == "1" and not restart:
        await message.answer(
            f"Мониторинг задания {job_id} уже запущен.", reply_markup=main_keyboard()
        )
        return

    reset = restart or job.get("status") in {"ready", "completed", "failed"}
    generation = await start_monitoring(
        redis,
        job_id=job_id,
        chat_id=message.chat.id,
        ttl_seconds=settings.job_ttl_seconds,
        interval_seconds=settings.recheck_interval_seconds,
        restart=reset,
    )
    try:
        await asyncio.to_thread(
            check_job.apply_async,
            args=[job_id, generation],
            task_id=f"link-monitor-{job_id}-{generation}-{uuid.uuid4().hex[:8]}",
        )
    except Exception:
        logger.exception("Не удалось поставить задание %s в очередь", job_id)
        await stop_monitoring(redis, job_id=job_id, ttl_seconds=settings.job_ttl_seconds)
        await message.answer(
            "Очередь временно недоступна. Повторите попытку позже.",
            reply_markup=main_keyboard(),
        )
        return


    action = "перезапущен" if restart else "запущен"
    await message.answer(
        f"Мониторинг {action}. Задание: {job_id}.\n"
        f"Недоступные ссылки будут перепроверяться каждые "
        f"{_format_interval(settings.recheck_interval_seconds)}",
        reply_markup=main_keyboard(),
    )


@router.message(F.text == START_SEARCH)
async def start_search(message: Message, settings: Settings, redis: Redis) -> None:
    await _launch_monitoring(message, settings, redis, restart=False)


@router.message(F.text == RESTART)
async def restart_search(message: Message, settings: Settings, redis: Redis) -> None:
    await _launch_monitoring(message, settings, redis, restart=True)


@router.message(F.text == STOP)
async def stop_search(message: Message, settings: Settings, redis: Redis) -> None:
    current = await get_chat_job(redis, message.chat.id)
    if current is None:
        await message.answer("Активная база не найдена.", reply_markup=main_keyboard())
        return
    job_id, job = current
    if job.get("monitoring") != "1":
        await message.answer("Мониторинг уже остановлен.", reply_markup=main_keyboard())
        return
    await stop_monitoring(redis, job_id=job_id, ttl_seconds=settings.job_ttl_seconds)
    await message.answer(
        f"Мониторинг задания {job_id} остановлен.", reply_markup=main_keyboard()
    )


@router.message(F.document)
async def document(message: Message, bot: Bot, settings: Settings, redis: Redis) -> None:
    attachment = message.document
    if attachment is None:
        return
    filename = attachment.file_name or ""
    if not filename.lower().endswith(".txt"):
        await message.answer("Поддерживаются только файлы с расширением .txt.")
        return
    if attachment.file_size is not None and attachment.file_size > settings.max_file_bytes:
        await message.answer(
            f"Файл слишком большой. Максимум: {settings.max_file_bytes:,} байт."
        )
        return

    current = await get_chat_job(redis, message.chat.id)
    if current is not None and current[1].get("monitoring") == "1":
        await message.answer(
            "Сначала остановите текущий мониторинг, затем загрузите новую базу.",
            reply_markup=main_keyboard(),
        )
        return

    downloaded = await bot.download(attachment)
    if downloaded is None:
        await message.answer("Telegram не вернул файл. Попробуйте ещё раз.")
        return
    data = downloaded.read(settings.max_file_bytes + 1)
    if len(data) > settings.max_file_bytes:
        await message.answer(
            f"Файл слишком большой. Максимум: {settings.max_file_bytes:,} байт."
        )
        return

    try:
        urls = parse_url_file(data, max_urls=settings.max_urls_per_file)
    except InputError as exc:
        translations = {
            "The file must be UTF-8 encoded.": "Файл должен быть в кодировке UTF-8.",
            "The file does not contain any links.": "Файл не содержит ссылок.",
        }
        error = str(exc)
        if error.startswith("The file contains more than"):
            error = f"В файле больше {settings.max_urls_per_file:,} непустых строк."
        await message.answer(translations.get(error, error))
        return

    job_id = uuid.uuid4().hex[:12]
    await create_job(
        redis,
        job_id=job_id,
        chat_id=message.chat.id,
        urls=urls,
        ttl_seconds=settings.job_ttl_seconds,
        interval_seconds=settings.recheck_interval_seconds,
    )
    unique_count = len({item.url for item in urls})
    duplicates = len(urls) - unique_count
    duplicate_note = f" Повторов: {duplicates:,}." if duplicates else ""
    await message.answer(
        f"База загружена: {len(urls):,} ссылок.{duplicate_note}\n"
        f"Задание: {job_id}. Нажмите «{START_SEARCH}».",
        reply_markup=main_keyboard(),
    )


@router.message()
async def unsupported(message: Message) -> None:
    await message.answer(
        "Выберите действие на клавиатуре или отправьте TXT-файл со ссылками.",
        reply_markup=main_keyboard(),
    )


async def run() -> None:
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    bot = Bot(token=settings.bot_token.get_secret_value())
    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    try:
        await redis.ping()
        await dispatcher.start_polling(bot, settings=settings, redis=redis)
    finally:
        await redis.aclose()
        await bot.session.close()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    asyncio.run(run())


if __name__ == "__main__":
    main()
