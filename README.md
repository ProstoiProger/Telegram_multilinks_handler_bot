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

1. Нажмите **«Загрузить t.me-список 📚»** и отправьте UTF-8 TXT-файл: одна t.me-ссылка
   в строке.
2. Нажмите **«Проверить t.me-ссылки 🔍»**.
3. Бот отправит Excel-файл с результатами. Команда `/status` показывает
   состояние задания, **«Остановить мониторинг»** прекращает мониторинг.

## Подготовка

### Требования

- Docker и Docker Compose;
- токен бота от [BotFather](https://t.me/BotFather);
- `API ID` и `API hash` Telegram-приложения из
  [my.telegram.org/apps](https://my.telegram.org/apps).

Последние два параметра нужны для MTProto-проверки публичных username. Бот
авторизуется собственным токеном; номер телефона, код входа и пользовательская
сессия не используются.

### Как получить API ID и API hash

1. Войдите в действующий личный аккаунт Telegram через
   [my.telegram.org](https://my.telegram.org).
2. Откройте раздел **API development tools**.
3. Заполните форму создания приложения:

   - **App title:** например, `Telegram Link Checker`;
   - **Short name:** например, `linkcheckerbot` — латинские буквы и цифры,
     без пробелов;
   - **URL:** адрес сайта проекта или `https://example.com`;
   - **Platform:** `Desktop` или `Other`;
   - **Description:** например, `Monitoring public Telegram links`.

4. После создания скопируйте значения **api_id** и **api_hash**.
5. Добавьте их в `.env` как `TELEGRAM_API_ID` и `TELEGRAM_API_HASH`.

Telegram использует эти параметры для авторизации MTProto-клиента, в том числе
при входе бота по его токену. Не публикуйте `api_hash`, токен бота или весь
`.env`.

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

## Настройки для одного пользователя

| Параметр | Рекомендуемое значение | Назначение |
| --- | ---: | --- |
| `CELERY_WORKER_CONCURRENCY` | `1` | Одновременно выполняется одно задание. |
| `CHECK_CONCURRENCY` | `10` | Число одновременных запросов к Telegram внутри задания. |
| `CHECK_TOTAL_TIMEOUT_SECONDS` | `5.0` | Тайм-аут одной проверки. |
| `RECHECK_INTERVAL_SECONDS` | `1800` | Интервал повторной проверки. |
| `MAX_URLS_PER_FILE` | `10000` | Максимум строк со ссылками. |
| `JOB_TTL_SECONDS` | `86400` | Срок хранения остановленного задания. |

Для 1 000 уникальных username начните с этих значений. Не повышайте
`CHECK_CONCURRENCY` выше `10–15` без замеров: Telegram ограничивает частоту
запросов. При ограничении бот сохранит ссылку для повторного контроля.

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
