from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

UPLOAD_DATABASE = "Загрузка базы 📚"
START_SEARCH = "Начать поиск 🔍"
STOP = "Остановить"


def main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=UPLOAD_DATABASE), KeyboardButton(text=START_SEARCH)],
            [KeyboardButton(text=STOP)],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Выберите действие",
    )
