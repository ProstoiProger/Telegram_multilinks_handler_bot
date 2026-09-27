from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

UPLOAD_DATABASE = "Загрузить t.me-список 📚"
START_SEARCH = "Проверить t.me-ссылки 🔍"
STOP = "Остановить мониторинг"

# Old keyboards remain visible in existing Telegram chats after a bot update.
LEGACY_UPLOAD_DATABASE = "Загрузка базы 📚"
LEGACY_START_SEARCH = "Начать поиск 🔍"
LEGACY_STOP = "Остановить"


def main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=UPLOAD_DATABASE), KeyboardButton(text=START_SEARCH)],
            [KeyboardButton(text=STOP)],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Выберите действие для t.me-ссылок",
    )
