from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "pdf" / "telegram_link_checker_pipeline.pdf"
FONT_DIR = Path("C:/Windows/Fonts")


def p(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(text, style)


def build() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    pdfmetrics.registerFont(TTFont("Arial", str(FONT_DIR / "arial.ttf")))
    pdfmetrics.registerFont(TTFont("Arial-Bold", str(FONT_DIR / "arialbd.ttf")))

    navy = colors.HexColor("#102A43")
    blue = colors.HexColor("#1677B8")
    light_blue = colors.HexColor("#EAF4FB")
    pale = colors.HexColor("#F5F7FA")
    dark = colors.HexColor("#243B53")
    muted = colors.HexColor("#627D98")
    orange = colors.HexColor("#D97706")
    red = colors.HexColor("#B42318")
    green = colors.HexColor("#047857")

    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "Title", parent=styles["Title"], fontName="Arial-Bold", fontSize=25,
        leading=30, textColor=navy, spaceAfter=10,
    )
    subtitle = ParagraphStyle(
        "Subtitle", parent=styles["Normal"], fontName="Arial", fontSize=11,
        leading=16, textColor=muted, spaceAfter=12,
    )
    h1 = ParagraphStyle(
        "H1", parent=styles["Heading1"], fontName="Arial-Bold", fontSize=17,
        leading=22, textColor=navy, spaceBefore=14, spaceAfter=8,
    )
    h2 = ParagraphStyle(
        "H2", parent=styles["Heading2"], fontName="Arial-Bold", fontSize=12,
        leading=16, textColor=blue, spaceBefore=10, spaceAfter=5,
    )
    body = ParagraphStyle(
        "Body", parent=styles["BodyText"], fontName="Arial", fontSize=9.4,
        leading=14, textColor=dark, spaceAfter=6,
    )
    small = ParagraphStyle(
        "Small", parent=body, fontSize=8, leading=10.5, textColor=muted,
    )
    bullet = ParagraphStyle(
        "Bullet", parent=body, leftIndent=12, firstLineIndent=-8, bulletIndent=0,
        spaceAfter=3,
    )
    code = ParagraphStyle(
        "Code", parent=body, fontName="Courier", fontSize=8.1, leading=11,
        backColor=colors.HexColor("#EFF3F8"), borderPadding=7, borderColor=colors.HexColor("#D9E2EC"),
        borderWidth=0.5, borderRadius=3, spaceBefore=3, spaceAfter=8,
    )
    callout = ParagraphStyle(
        "Callout", parent=body, fontName="Arial-Bold", textColor=navy,
        backColor=light_blue, borderPadding=9, borderColor=colors.HexColor("#B6D8EF"),
        borderWidth=0.5, borderRadius=4, spaceBefore=5, spaceAfter=10,
    )
    warning = ParagraphStyle(
        "Warning", parent=body, fontName="Arial-Bold", textColor=red,
        backColor=colors.HexColor("#FFF1F0"), borderPadding=9, borderColor=colors.HexColor("#F4C7C3"),
        borderWidth=0.5, borderRadius=4, spaceBefore=5, spaceAfter=10,
    )

    def table(rows: list[list[str]], widths: list[float], header: bool = True) -> Table:
        content = [[p(cell, small if not header or index else ParagraphStyle(
            "TableHeader", parent=small, fontName="Arial-Bold", textColor=colors.white
        )) for cell in row] for index, row in enumerate(rows)]
        result = Table(content, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
        style = [
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D9E2EC")),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("BACKGROUND", (0, 1), (-1, -1), colors.white),
        ]
        if header:
            style += [("BACKGROUND", (0, 0), (-1, 0), navy)]
        result.setStyle(TableStyle(style))
        return result

    def flow_row(items: list[tuple[str, str]], color: colors.Color = light_blue) -> Table:
        cells = []
        for heading, description in items:
            cells.append(p(f"<b>{heading}</b><br/>{description}", body))
        result = Table([cells], colWidths=[170 * mm / len(cells)] * len(cells), hAlign="LEFT")
        result.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), color),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#B6D8EF")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#B6D8EF")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ]))
        return result

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#D9E2EC"))
        canvas.line(doc.leftMargin, 13 * mm, A4[0] - doc.rightMargin, 13 * mm)
        canvas.setFont("Arial", 7.5)
        canvas.setFillColor(muted)
        canvas.drawString(doc.leftMargin, 8.5 * mm, "Telegram Link Checker - технический паспорт")
        canvas.drawRightString(A4[0] - doc.rightMargin, 8.5 * mm, f"Страница {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(
        str(OUTPUT), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=18 * mm, bottomMargin=19 * mm, title="Telegram Link Checker - пайплайн проекта",
        author="Проект Telegram Link Checker",
    )
    story = []
    story += [
        Spacer(1, 8 * mm),
        p("Telegram Link Checker", title),
        p("Технический паспорт: архитектура, пайплайн, лимиты, эксплуатация и выбор сервера", subtitle),
        p("Версия документа: 16 октября 2026. Основание по фактической нагрузке: raw.txt, интервал 11-14 октября 2026.", small),
        Spacer(1, 8),
        p("Ключевой вывод", h1),
        p("Для одного владельца бот технически лёгкий: его скорость ограничена не CPU, а сетью и лимитами Telegram. Для отдельного сервера достаточно 1 vCPU / 2 GB RAM / 20 GB SSD, однако наиболее практичная покупка - 2 vCPU / 4 GB RAM / 40 GB SSD: это запас на обновления, сборку Docker-образов, Redis и рост логов, а не способ ускорить запросы к Telegram.", callout),
        p("Документ описывает фактическую реализацию репозитория на момент подготовки. Пиковая пользовательская нагрузка в raw.txt отсутствует, поэтому расчёты по RAM и серверу являются инженерной оценкой, а не результатом стресс-теста.", warning),
        p("Содержание", h1),
    ]
    contents = [
        "1. Назначение и границы системы",
        "2. Состав и технологии",
        "3. Пайплайн пользовательского запроса",
        "4. Пайплайн мониторинга и очередей",
        "5. Проверка t.me и классификация результатов",
        "6. Временные пределы и конфигурация",
        "7. Защита, устойчивость и состояние",
        "8. Нагрузка из raw.txt и выбор сервера",
        "9. Эксплуатационный чек-лист",
    ]
    for item in contents:
        story.append(Paragraph(item, bullet, bulletText="•"))
    story.append(PageBreak())

    story += [
        p("1. Назначение и границы системы", h1),
        p("Сервис принимает TXT-файл с публичными ссылками Telegram и определяет, существует ли указанный публичный username. Поддерживаются только публичные HTTP(S)-ссылки на t.me, www.t.me, telegram.me и www.telegram.me. Цель проверки - наличие сущности Telegram: пользователя, бота, канала или публичной группы.", body),
        p("Это не HTTP-проверка страницы t.me. Бот обращается к Telegram API через Telethon и вызывает разрешение username. Поэтому статус отражает ответ Telegram, а не доступность веб-страницы через браузер.", callout),
        p("Не поддерживаются приватные инвайты, ссылки с +, joinchat, c, addstickers, addemoji, share, iv, proxy, login, boost и другие сервисные маршруты. Username обязан начинаться с буквы, иметь 5-32 символа и состоять из латинских букв, цифр и подчёркивания.", body),
        p("2. Состав и технологии", h1),
        table([
            ["Компонент", "Технология", "Роль"],
            ["Telegram UI", "aiogram 3.26+", "Long polling, команды, кнопки, загрузка документа и фильтр владельца."],
            ["Проверка username", "Telethon 1.42+", "Авторизованный запрос к Telegram API и get_entity(username)."],
            ["Фоновые задачи", "Celery 5.5+", "Постановка и выполнение первичных и повторных проверок."],
            ["Планировщик", "Celery Beat", "Каждые 5 секунд находит задания, срок которых наступил."],
            ["Хранилище / брокер", "Redis 7.4 Alpine", "Очередь Celery, метаданные заданий, списки ссылок, блокировки и расписание."],
            ["Конфигурация", "Pydantic Settings 2.7+", "Чтение и валидация переменных .env."],
            ["Упаковка", "Docker Compose", "Изолированные сервисы: redis, bot, worker, beat, session-init."],
            ["Язык и контроль качества", "Python 3.12, pytest, Ruff, mypy", "Логика, тесты, линтинг и статическая типизация."],
        ], [38 * mm, 40 * mm, 92 * mm]),
        p("Все прикладные контейнеры используют один Docker-образ. Сервис session-init от root создаёт каталог сессии и передаёт права непривилегированному UID 10001; bot, worker и beat запускаются как этот отдельный пользователь.", body),
    ]
    story.append(PageBreak())

    story += [
        p("3. Пайплайн пользовательского запроса", h1),
        flow_row([
            ("1. Доступ", "aiogram принимает только личный чат, где from_user.id и chat.id совпадают с ALLOWED_TELEGRAM_USER_ID."),
            ("2. Файл", "TXT до 2 MB, UTF-8/UTF-8 BOM. Пустые строки и комментарии # пропускаются."),
            ("3. Задание", "Ссылки и метаданные сохраняются в Redis; создаётся идентификатор задания."),
        ]),
        Spacer(1, 5),
        flow_row([
            ("4. Запуск", "Кнопка запуска включает мониторинг, повышает generation и ставит первичную задачу Celery."),
            ("5. Проверка", "Worker открывает устойчивую Telethon-сессию и разрешает уникальные username."),
            ("6. Результат", "В личный чат уходят только новые ненайденные username и предупреждение FloodWait."),
        ], colors.HexColor("#F0FDF4")),
        Spacer(1, 7),
        p("Дубликаты не создают лишних запросов: в пределах цикла сначала строится набор уникальных URL, а затем один результат разворачивается обратно для всех строк исходного файла. В самом сообщении отсутствующие username также дедуплицируются.", body),
    ]

    story += [
        p("4. Пайплайн мониторинга и очередей", h1),
        p("После старта задание хранит generation, статус, число строк, список всех ссылок, список ссылок для повторной проверки, план следующего запуска и временные метки. В Redis используется sorted set с моментом запуска. Beat не проверяет ссылки сам: он лишь раз в 5 секунд передаёт просроченные задания worker-у.", body),
        flow_row([
            ("Beat: 5 сек", "dispatch_due_jobs читает до 100 просроченных job ID, планирует следующий запуск и публикует check_job."),
            ("Worker", "Берёт Redis-lock конкретного задания. Повторный запуск того же job параллельно возвращает already_running."),
            ("Generation", "Стоп или перезапуск повышает поколение. Устаревшая задача не может перезаписать актуальное состояние."),
        ]),
        p("Логика двух контуров", h2),
        table([
            ["Контур", "Что проверяется", "Период", "Зачем"],
            ["Первичная проверка", "Весь файл", "Сразу после нажатия «Начать поиск»", "Сформировать исходное состояние."],
            ["Быстрый повтор", "Не найденные и временные ошибки", "20 секунд", "Быстро заметить появление ранее отсутствующего username или восстановление сети."],
            ["Полный повтор", "Весь исходный файл, включая найденные", "60 секунд", "Обнаружить username, который существовал, а затем исчез."],
        ], [35 * mm, 52 * mm, 28 * mm, 55 * mm]),
        p("Если ранее найденный username во время полного цикла перестал разрешаться, он попадает в обычный список ненайденных. Специального сообщения об изменении статуса или Excel-отчёта система не формирует.", body),
        p("Celery настроен с task_acks_late, task_reject_on_worker_lost, prefetch multiplier = 1 и повтором подключения к брокеру. Это уменьшает риск потери задачи и не даёт одному worker заранее забрать большую пачку задач. Redis-lock имеет время жизни 700 секунд; при аварии он сам освободится.", body),
        p("5. Проверка t.me и классификация результатов", h1),
        table([
            ["Состояние", "Причина", "Дальнейшее действие"],
            ["WORKING", "Telegram вернул User, Channel или Chat", "Не попадает в быстрый повтор, но попадёт в полный цикл."],
            ["BROKEN", "UsernameNotOccupiedError или отсутствие сущности", "Username отправляется владельцу и будет перепроверяться."],
            ["INVALID", "Некорректная ссылка или формат username", "Не является публичным username; не следует исправлять сетью."],
            ["TIMEOUT", "Запрос вышел за лимит времени либо активен FloodWait", "Попадает в повтор; FloodWait включает паузу."],
            ["NETWORK_ERROR", "RPC, ОС или соединение", "Попадает в повторную проверку."],
        ], [32 * mm, 68 * mm, 70 * mm]),
        p("На один check_all создаётся TelegramClient с durable SQLite-сессией по TELEGRAM_SESSION_PATH. Сессия хранится в именованном Docker volume telethon-session-data, поэтому при перезапуске контейнера не создаётся новая память-сессия. При текущем CELERY_WORKER_CONCURRENCY=1 доступ к этой сессии последовательный.", body),
    ]

    story += [
        p("6. Временные пределы и конфигурация", h1),
        table([
            ["Переменная", "Текущее / по умолчанию", "Граница в коде", "Смысл"],
            ["ALLOWED_TELEGRAM_USER_ID", "задаёт владелец", "обязателен для bot", "Единственный личный чат, с которым бот работает."],
            ["CHECK_CONCURRENCY", "1", "1-20", "Одновременные разрешения username в одном worker."],
            ["CHECK_TOTAL_TIMEOUT_SECONDS", "5.0 сек", ">0, до 120 сек", "Тайм-аут одного get_entity."],
            ["RECHECK_INTERVAL_SECONDS", "20 сек", "15 сек - 24 ч", "Период быстрых повторов."],
            ["WORKING_RECHECK_INTERVAL_SECONDS", "60 сек", "60 сек - 24 ч", "Период полного обхода."],
            ["MONITOR_DISPATCH_INTERVAL_SECONDS", "5 сек", "5-300 сек", "Частота работы Beat."],
            ["MONITOR_LOCK_TIMEOUT_SECONDS", "700 сек", "60-3600 сек", "TTL блокировки job в Redis."],
            ["MAX_FILE_BYTES", "2 MiB", "1 B - 20 MiB", "Максимальный размер TXT."],
            ["MAX_URLS_PER_FILE", "10 000", "1 - 100 000", "Максимум непустых строк."],
            ["JOB_TTL_SECONDS", "86 400 сек (24 ч)", "60 сек - 7 дней", "Время хранения job и списков Redis."],
        ], [43 * mm, 40 * mm, 34 * mm, 53 * mm]),
        p("Лимиты Celery", h2),
        p("Мягкий лимит задачи - 600 секунд, жёсткий - 630 секунд. visibility timeout брокера равен monitor lock timeout + 60 секунд, то есть по умолчанию 760 секунд. Graceful shutdown worker-а - 30 секунд. Эти значения важны при больших файлах: 10 000 строк допустимы как входной размер, но не гарантируют завершение полного цикла за минуту или даже за 10 минут.", body),
        KeepTogether([
            p("FloodWait", h2),
            p("Telethon создаётся с flood_sleep_threshold=0: библиотека не «засыпает» молча, а сразу возвращает FloodWaitError. Код запоминает время окончания паузы, помечает результаты как временную ошибку и уведомляет владельца с округлённым количеством минут. Пока сервер Telegram не разрешит продолжить, новые Telegram-запросы не выполняются.", callout),
            p("Точный лимит запросов Telegram не фиксирован в коде и не должен считаться контрактом: он зависит от аккаунта, истории запросов и ответа серверов Telegram. Поэтому увеличение CPU или CHECK_CONCURRENCY выше 1 не является безопасным способом ускорения. Менять параллелизм следует только после измерений без FloodWait.", warning),
        ]),
        p("7. Защита, устойчивость и состояние", h1),
        table([
            ["Механизм", "Практический эффект"],
            ["Ограничение владельцем", "Router принимает только личный чат с ALLOWED_TELEGRAM_USER_ID; фоновые отправки повторно проверяют chat_id."],
            ["Постоянная сессия", "Снижает риск проблем от повторного создания MemorySession и переживает перезапуск worker-а."],
            ["Redis AOF + noeviction", "Состояние записывается на диск; Redis не удаляет ключи под давлением памяти, но требует контроля RAM."],
            ["Lock + generation", "Не допускают два параллельных цикла одного задания и отсеивают устаревшие задачи."],
            ["Валидация ввода", "Только UTF-8 TXT, размер/строки ограничены, приватные и сервисные t.me-маршруты исключены."],
            ["Непривилегированный runtime", "Основные контейнеры работают от UID 10001, а root используется только для одноразовой инициализации каталога сессии."],
        ], [52 * mm, 118 * mm]),
    ]
    story.append(PageBreak())

    story += [
        p("8. Нагрузка из raw.txt и выбор сервера", h1),
        p("Наблюдаемое окно в raw.txt: 11 октября 2026, 04:33 - 14 октября 2026, 09:50 (около 77 часов). В этот период пользовательских проверок не было: 0 задач, 0 проверенных ссылок, 0 FloodWait. Поэтому эти метрики характеризуют режим ожидания, а не массовую проверку.", body),
        table([
            ["Показатель из raw.txt", "Значение", "Интерпретация"],
            ["Служебные циклы Beat", "55 638", "Планировщик исправно опрашивал просроченные задания."],
            ["Среднее время цикла", "2.46 ms", "Практически нулевая CPU-нагрузка при простое."],
            ["Максимум цикла", "79.5 ms", "Нет признака CPU-узкого места в режиме ожидания."],
            ["Суммарное время циклов", "около 137 сек", "Оценочно около 0.05% времени одного ядра за окно."],
            ["Redis / Telethon session", "23 MB / 40 KB", "Состояние проекта компактно при текущем наборе job."],
            ["Логи контейнеров", "около 36 MB; рост ~11 MB/сутки", "Главный долгосрочный риск - отсутствие ротации."],
        ], [52 * mm, 42 * mm, 76 * mm]),
        p("Ожидаемая RAM по raw.txt: bot 50-100 MB, worker 120-250 MB, beat 50-100 MB, Redis 20-100 MB, Docker и Linux 250-500 MB. Итого ориентир 500-900 MB. На 1 GB система может работать, но почти без запаса на обновления и крупные операции Docker.", body),
        p("Рекомендация по покупке", h2),
        table([
            ["Профиль", "Конфигурация", "Когда выбирать"],
            ["Достаточно", "1 vCPU, 2 GB RAM, 20 GB SSD, 100 Mbit/s, Debian 12/Ubuntu 24.04", "Один владелец, CHECK_CONCURRENCY=1, включена ротация логов."],
            ["Рекомендовано", "2 vCPU, 4 GB RAM, 40 GB SSD, 100 Mbit/s", "Разница в цене невелика; комфортнее обновления, сборки образов, диагностика и запас по диску."],
            ["Не даёт пользы сейчас", "4+ vCPU ради скорости проверки", "Ограничение находится у Telegram API и сети, а не на CPU."],
        ], [36 * mm, 72 * mm, 62 * mm]),
        p("Текущий сервер из raw.txt имеет 2 vCPU, 3.8 GB RAM и 48 GB диска - ресурсы CPU/RAM для проекта достаточны. Свободно около 4.7 GB, заполнение диска 91%; проблема не в мощности, а в запасе диска и логах. На чистом отдельном VPS 20 GB достаточно при ротации, но 40 GB - разумнее для спокойной эксплуатации.", callout),
        p("Ротация Docker-логов", h2),
        p("В raw.txt указан драйвер json-file без ограничения размера. Это может заполнить диск. Добавьте к каждому сервису Docker Compose или в daemon-конфигурацию следующее ограничение:", body),
        p('logging:\n  driver: local\n  options:\n    max-size: "10m"\n    max-file: "3"', code),
        p("После применения следите за df -h, docker system df, docker compose logs, Redis memory и числом ожидающих заданий. Если оставляете INFO-логи Celery, ротация обязательна.", body),
        KeepTogether([
            p("9. Эксплуатационный чек-лист", h1),
            table([
            ["Перед запуском", "Во время работы", "При инциденте"],
            ["Заполнить BOT_TOKEN, ALLOWED_TELEGRAM_USER_ID, TELEGRAM_API_ID, TELEGRAM_API_HASH. Не коммитить .env.", "Проверять docker compose ps, свободный диск, Redis и наличие FloodWait в логах.", "При FloodWait не увеличивать concurrency; ждать время из уведомления Telegram."],
            ["Убедиться, что telethon-session-data сохраняется между обновлениями.", "Оставить CELERY_WORKER_CONCURRENCY=1 и CHECK_CONCURRENCY=1 для одного аккаунта.", "При ошибках сети проверить DNS/исходящий TCP к Telegram и состояние контейнеров."],
            ["Включить ротацию логов до долгой эксплуатации.", "Перед обновлением сделать резервную копию Redis volume и Telethon session volume.", "При дефиците места сначала проверить Docker-логи и не удалять volume сессии без необходимости."],
            ], [56 * mm, 56 * mm, 58 * mm]),
        ]),
        Spacer(1, 8),
        p("Итог: для текущей модели «один владелец, одна постоянная Telegram-сессия, последовательные запросы» сервер с 2 vCPU / 4 GB RAM / 40 GB SSD будет комфортным и консервативным выбором. Если бюджет критичен и ротация логов включена, 1 vCPU / 2 GB / 20 GB технически достаточно.", callout),
        p("Источник измерений: raw.txt. Параметры пайплайна и конфигурации: исходный код и Compose-конфигурация проекта на 16 октября 2026.", small),
    ]
    doc.build(story, onFirstPage=footer, onLaterPages=footer)


if __name__ == "__main__":
    build()
