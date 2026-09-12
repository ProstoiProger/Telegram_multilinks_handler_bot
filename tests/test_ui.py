from link_checker.ui import START_SEARCH, STOP, UPLOAD_DATABASE, main_keyboard


def test_main_keyboard_matches_reference_layout() -> None:
    keyboard = main_keyboard()
    assert [[button.text for button in row] for row in keyboard.keyboard] == [
        [UPLOAD_DATABASE, START_SEARCH],
        [STOP],
    ]
    assert keyboard.resize_keyboard is True
    assert keyboard.is_persistent is True
