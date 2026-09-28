import time
from pathlib import Path

import pytest

from link_checker.checker import LinkChecker
from link_checker.config import Settings
from link_checker.models import LinkResult, LinkState
from link_checker.parser import InputUrl
from link_checker.security import InvalidUrlError
from link_checker.telegram_links import extract_public_username


@pytest.mark.parametrize(
    ("url", "username"),
    [
        ("https://t.me/Telegram", "telegram"),
        ("https://t.me/s/Telegram/123", "telegram"),
        ("http://telegram.me/Test_User", "test_user"),
        ("https://www.t.me/TestUser?start=1", "testuser"),
    ],
)
def test_extracts_username_from_public_telegram_link(url: str, username: str) -> None:
    assert extract_public_username(url) == username


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/Telegram",
        "https://t.me/+privateInvite",
        "https://t.me/joinchat/privateInvite",
        "https://t.me/share/url?url=https://example.com",
        "https://t.me/abc",
    ],
)
def test_rejects_non_public_or_invalid_telegram_link(url: str) -> None:
    with pytest.raises(InvalidUrlError):
        extract_public_username(url)


@pytest.mark.asyncio
async def test_reports_missing_telegram_api_credentials() -> None:
    checker = LinkChecker(
        Settings(bot_token="123456:unit-test", telegram_api_id=0, telegram_api_hash="")
    )
    result = (await checker.check_all([InputUrl(1, "https://t.me/Telegram")]))[0]

    assert result.state is LinkState.NETWORK_ERROR
    assert result.is_working is False
    assert result.error == "TELEGRAM_API_ID and TELEGRAM_API_HASH are not configured"


@pytest.mark.asyncio
async def test_checker_only_checks_duplicate_once(monkeypatch: pytest.MonkeyPatch) -> None:
    checker = LinkChecker(
        Settings(bot_token="123456:unit-test", telegram_api_id=1, telegram_api_hash="x")
    )
    calls = 0

    async def fake_resolve(urls: list[InputUrl]) -> list[LinkResult]:
        nonlocal calls
        calls += len(urls)
        return [
            checker._failure(item, LinkState.BROKEN, 0, "Telegram username not found")
            for item in urls
        ]

    monkeypatch.setattr(checker, "_resolve_unique", fake_resolve)
    results = await checker.check_all(
        [InputUrl(1, "https://t.me/Telegram"), InputUrl(9, "https://t.me/Telegram")]
    )

    assert calls == 1
    assert [result.line_number for result in results] == [1, 9]


def test_uses_a_persistent_session_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session_path = tmp_path / "telethon" / "bot"
    checker = LinkChecker(
        Settings(
            bot_token="123456:unit-test",
            telegram_api_id=1,
            telegram_api_hash="x",
            telegram_session_path=session_path,
        )
    )
    captured: dict[str, object] = {}

    def fake_client(*args: object, **kwargs: object) -> object:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr("link_checker.checker.TelegramClient", fake_client)

    checker._create_client()

    assert session_path.parent.is_dir()
    assert captured["args"] == (str(session_path), 1, "x")
    assert captured["kwargs"] == {"flood_sleep_threshold": 0}


@pytest.mark.asyncio
async def test_does_not_call_telegram_while_flood_wait_is_active(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checker = LinkChecker(
        Settings(bot_token="123456:unit-test", telegram_api_id=1, telegram_api_hash="x")
    )
    monkeypatch.setattr(LinkChecker, "_flood_wait_until", time.monotonic() + 30)

    def fail_if_client_is_created() -> None:
        raise AssertionError("Telegram must not be called during FloodWait")

    monkeypatch.setattr(checker, "_create_client", fail_if_client_is_created)

    result = await checker._resolve_unique([InputUrl(1, "https://t.me/Telegram")])

    assert result[0].state is LinkState.TIMEOUT
    assert result[0].error is not None
    assert result[0].error.startswith("Telegram flood wait:")
