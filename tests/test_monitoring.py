import time
from collections.abc import Sequence

import pytest

from link_checker import tasks
from link_checker.models import LinkResult, LinkState
from link_checker.parser import InputUrl


async def _ignore_text(chat_id: int, text: str) -> None:
    return None


class FakeStore:
    def __init__(self, results_urls: Sequence[InputUrl], *, cycle: int = 0) -> None:
        self.job = {
            "monitoring": "1",
            "generation": "7",
            "cycle": str(cycle),
            "total": str(len(results_urls)),
            "working": "0",
        }
        self.urls = list(results_urls)
        self.retry_urls = list(results_urls)
        self.unscheduled = False

    def get(self, job_id: str) -> dict[str, str]:
        return self.job

    def get_urls(self, job_id: str) -> list[InputUrl]:
        return self.urls

    def get_retry_urls(self, job_id: str) -> list[InputUrl]:
        return self.retry_urls

    def is_current(self, job_id: str, generation: int) -> bool:
        return self.job["monitoring"] == "1" and generation == int(self.job["generation"])

    def set_retry_urls(self, job_id: str, urls: Sequence[InputUrl]) -> None:
        self.retry_urls = list(urls)

    def update(self, job_id: str, **values: object) -> None:
        self.job.update({key: str(value) for key, value in values.items()})

    def unschedule(self, job_id: str) -> None:
        self.unscheduled = True


def test_missing_username_messages_are_deduplicated() -> None:
    messages = tasks._missing_username_messages(
        [
            LinkResult(1, "https://t.me/missing_user", False, LinkState.BROKEN),
            LinkResult(2, "https://t.me/missing_user", False, LinkState.BROKEN),
            LinkResult(3, "https://t.me/found_user", True, LinkState.WORKING),
        ]
    )

    assert messages == ["@missing_user"]


@pytest.mark.asyncio
async def test_initial_cycle_retries_only_transient_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    urls = [InputUrl(index, f"https://example.com/{index}") for index in range(1, 7)]
    results = [
        LinkResult(1, urls[0].url, True, LinkState.WORKING, 200),
        LinkResult(2, urls[1].url, True, LinkState.RESTRICTED, 403),
        LinkResult(3, urls[2].url, False, LinkState.BROKEN, 404),
        LinkResult(4, urls[3].url, False, LinkState.TIMEOUT),
        LinkResult(5, urls[4].url, False, LinkState.INVALID),
        LinkResult(6, urls[5].url, False, LinkState.BLOCKED),
    ]
    store = FakeStore(urls)

    async def fake_check_all(self: object, input_urls: Sequence[InputUrl]) -> list[LinkResult]:
        return results

    sent_texts: list[str] = []

    async def fake_send_text(chat_id: int, text: str) -> None:
        sent_texts.append(text)

    monkeypatch.setattr(tasks.LinkChecker, "check_all", fake_check_all)
    monkeypatch.setattr(tasks, "_send_text", fake_send_text)

    checked, recovered = await tasks._check_cycle("job", 7, store, 123)

    assert (checked, recovered) == (6, 2)
    assert [(item.line_number, item.url) for item in store.retry_urls] == [
        (3, urls[2].url),
        (4, urls[3].url),
    ]
    assert store.job["status"] == "monitoring"
    assert store.job["pending"] == "2"
    assert store.job["cycle"] == "1"
    assert sent_texts == ["https://example.com/3"]


@pytest.mark.asyncio
async def test_full_periodic_cycle_keeps_monitoring_when_all_usernames_are_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    urls = [InputUrl(3, "https://example.com/3"), InputUrl(4, "https://example.com/4")]
    store = FakeStore(urls, cycle=1)
    store.job.update({"total": "2", "working": "0"})
    results = [
        LinkResult(3, urls[0].url, True, LinkState.WORKING, 200),
        LinkResult(4, urls[1].url, True, LinkState.WORKING, 200),
    ]

    async def fake_check_all(self: object, input_urls: Sequence[InputUrl]) -> list[LinkResult]:
        return results

    monkeypatch.setattr(tasks.LinkChecker, "check_all", fake_check_all)
    monkeypatch.setattr(tasks, "_send_text", _ignore_text)

    await tasks._check_cycle("job", 7, store, 123)

    assert store.retry_urls == []
    assert store.job["status"] == "monitoring"
    assert store.job["monitoring"] == "1"
    assert store.job["pending"] == "0"
    assert store.job["working"] == "2"
    assert store.unscheduled is False
    assert float(store.job["next_full_check_at"]) > time.time()


@pytest.mark.asyncio
async def test_periodic_cycle_sends_missing_usernames_even_when_nothing_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    urls = [InputUrl(3, "https://t.me/missing_user")]
    store = FakeStore(urls, cycle=1)
    result = LinkResult(3, urls[0].url, False, LinkState.BROKEN)
    sent_texts: list[str] = []

    async def fake_check_all(self: object, input_urls: Sequence[InputUrl]) -> list[LinkResult]:
        return [result]

    async def fake_send_text(chat_id: int, text: str) -> None:
        sent_texts.append(text)

    monkeypatch.setattr(tasks.LinkChecker, "check_all", fake_check_all)
    monkeypatch.setattr(tasks, "_send_text", fake_send_text)

    await tasks._check_cycle("job", 7, store, 123)

    assert sent_texts == ["@missing_user"]


@pytest.mark.asyncio
async def test_between_full_checks_only_missing_usernames_are_checked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    found_url = InputUrl(1, "https://t.me/found_user")
    missing_url = InputUrl(2, "https://t.me/missing_user")
    store = FakeStore([found_url, missing_url], cycle=1)
    store.retry_urls = [missing_url]
    store.job.update(
        {
            "total": "2",
            "working": "1",
            "next_full_check_at": str(time.time() + 60),
        }
    )
    checked: list[InputUrl] = []

    async def fake_check_all(self: object, input_urls: Sequence[InputUrl]) -> list[LinkResult]:
        checked.extend(input_urls)
        return [LinkResult(2, missing_url.url, False, LinkState.BROKEN)]

    monkeypatch.setattr(tasks.LinkChecker, "check_all", fake_check_all)
    monkeypatch.setattr(tasks, "_send_text", _ignore_text)

    await tasks._check_cycle("job", 7, store, 123)

    assert checked == [missing_url]
    assert store.job["working"] == "1"
    assert store.retry_urls == [missing_url]


@pytest.mark.asyncio
async def test_flood_wait_is_reported_once_and_pauses_future_cycles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = InputUrl(1, "https://t.me/missing_user")
    store = FakeStore([url])
    sent_flood_waits: list[int] = []
    calls = 0

    async def fake_check_all(self: object, input_urls: Sequence[InputUrl]) -> list[LinkResult]:
        nonlocal calls
        calls += 1
        return [
            LinkResult(
                1,
                url.url,
                False,
                LinkState.TIMEOUT,
                error="Telegram flood wait: 125s",
            )
        ]

    async def fake_send_flood_wait(*, chat_id: int, seconds: int) -> None:
        sent_flood_waits.append(seconds)

    monkeypatch.setattr(tasks.LinkChecker, "check_all", fake_check_all)
    monkeypatch.setattr(tasks, "_send_text", _ignore_text)
    monkeypatch.setattr(tasks, "_send_flood_wait", fake_send_flood_wait)

    await tasks._check_cycle("job", 7, store, 123)
    await tasks._check_cycle("job", 7, store, 123)

    assert calls == 1
    assert sent_flood_waits == [125]
    assert float(store.job["flood_wait_until"]) > time.time()
