from collections.abc import Sequence

import pytest

from link_checker import tasks
from link_checker.models import LinkResult, LinkState
from link_checker.parser import InputUrl


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

    async def fake_send_report(**kwargs: object) -> int:
        return 42

    monkeypatch.setattr(tasks.LinkChecker, "check_all", fake_check_all)
    monkeypatch.setattr(tasks, "_send_report", fake_send_report)

    checked, recovered = await tasks._check_cycle("job", 7, store, 123)

    assert (checked, recovered) == (6, 2)
    assert [(item.line_number, item.url) for item in store.retry_urls] == [
        (3, urls[2].url),
        (4, urls[3].url),
    ]
    assert store.job["status"] == "monitoring"
    assert store.job["pending"] == "2"
    assert store.job["cycle"] == "1"
    assert store.job["report_message_id"] == "42"


@pytest.mark.asyncio
async def test_periodic_cycle_stops_when_all_retry_urls_recover(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    urls = [InputUrl(3, "https://example.com/3"), InputUrl(4, "https://example.com/4")]
    store = FakeStore(urls, cycle=1)
    store.job.update({"total": "6", "working": "2"})
    results = [
        LinkResult(3, urls[0].url, True, LinkState.WORKING, 200),
        LinkResult(4, urls[1].url, True, LinkState.WORKING, 200),
    ]

    async def fake_check_all(self: object, input_urls: Sequence[InputUrl]) -> list[LinkResult]:
        return results

    async def fake_send_report(**kwargs: object) -> int:
        return 43

    monkeypatch.setattr(tasks.LinkChecker, "check_all", fake_check_all)
    monkeypatch.setattr(tasks, "_send_report", fake_send_report)

    await tasks._check_cycle("job", 7, store, 123)

    assert store.retry_urls == []
    assert store.job["status"] == "completed"
    assert store.job["monitoring"] == "0"
    assert store.job["pending"] == "0"
    assert store.job["working"] == "4"
    assert store.unscheduled is True
