# Telegram-бот для мониторинга публичных t.me-ссылок

Бот принимает TXT-файл с публичными ссылками Telegram, определяет существование
пользователей, ботов, каналов и групп и отправляет XLSX-отчёт. Недоступные
username и временные ошибки Telegram периодически перепроверяются.

## Что проверяется

Поддерживаются публичные ссылки:

- `https://t.me/username`;
- `https://t.me/s/username`;
- ссылки на публичные сообщения: `https://t.me/username/123`.

Для каждой ссылки бот получает тип найденного объекта: `user`, `bot`,
`channel` или `group`.

Не поддерживаются инвайт-ссылки и служебные ссылки Telegram — например,
`t.me/+...`, `t.me/joinchat/...`, `t.me/c/...`, `t.me/share/...`.
Они не позволяют проверить существование публичного username.

## Как пользоваться

1. Нажмите **«Загрузка базы 📚»** и отправьте UTF-8 TXT-файл: одна t.me-ссылка
   в строке.
2. Нажмите **«Начать поиск 🔍»**.
3. Бот отправит Excel-файл с результатами. Команда `/status` показывает
   состояние задания, **«Остановить»** прекращает мониторинг.

## Подготовка

### Требования

- Docker и Docker Compose;
- токен бота от [BotFather](https://t.me/BotFather);
- `API ID` и `API hash` Telegram-приложения из
  [my.telegram.org/apps](https://my.telegram.org/apps).

Последние два параметра нужны для MTProto-проверки публичных username. Бот
авторизуется собственным токеном; номер телефона, код входа и пользовательская
сессия не используются.

### Настройка и запуск

1. Скопируйте конфигурацию:

   ```powershell
   Copy-Item .env.example .env
   ```

2. Заполните в `.env`:

   ```env
   BOT_TOKEN=123456789:токен-бота
   TELEGRAM_API_ID=123456
   TELEGRAM_API_HASH=ваш-api-hash
   ```

3. Запустите сервисы:

   ```bash
   docker compose up --build -d
   docker compose ps
   docker compose logs -f bot worker beat
   ```

После изменения `.env` примените конфигурацию командой
`docker compose up -d`.

## Настройки

| Параметр | По умолчанию | Назначение |
| --- | ---: | --- |
| `CHECK_CONCURRENCY` | `5` | Число одновременных запросов к Telegram. |
| `CHECK_TOTAL_TIMEOUT_SECONDS` | `5.0` | Тайм-аут одной проверки. |
| `RECHECK_INTERVAL_SECONDS` | `1800` | Интервал повторной проверки. |
| `MAX_URLS_PER_FILE` | `10000` | Максимум строк со ссылками. |
| `JOB_TTL_SECONDS` | `86400` | Срок хранения остановленного задания. |

Не повышайте `CHECK_CONCURRENCY` без необходимости: Telegram ограничивает
частоту запросов. При ограничении бот сохранит ссылку для повторного контроля.

## Результаты и повторные проверки

- **Доступна** — публичный Telegram-объект найден.
- **Не работает** — username не найден.
- **Некорректна** — ссылка не является поддерживаемой публичной t.me-ссылкой.
- **Тайм-аут / ошибка сети** — временная ошибка соединения или лимит Telegram.

На повторный контроль ставятся отсутствующие username, тайм-ауты и сетевые
ошибки: username может стать доступным позднее.

## Архитектура

```text
Telegram → aiogram bot → Redis → Celery worker → Telegram MTProto
                              ↑                    │
                         Celery Beat ← планировщик  ↓
                                               XLSX → Telegram
```

Redis хранит задания и расписание. Celery worker выполняет проверку, а Celery
Beat запускает повторные циклы. Для одного развёртывания должен работать только
один экземпляр Celery Beat.

## Проверка проекта

```bash
docker compose --profile tools run --rm test
docker compose --profile tools run --rm test ruff check src tests scripts
docker compose --profile tools run --rm test mypy src
```
