import socket

import httpx
import pytest

from link_checker.checker import LinkChecker
from link_checker.config import Settings
from link_checker.models import LinkState
from link_checker.parser import InputUrl
from link_checker.security import DnsGuard


async def public_resolver(host: str, port: int) -> list[tuple[object, ...]]:
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]


def settings() -> Settings:
    return Settings(bot_token="123456:unit-test", check_concurrency=20)


@pytest.mark.asyncio
async def test_checker_follows_redirects_and_classifies_results() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/redirect":
            return httpx.Response(302, headers={"location": "/ok"})
        if request.url.path == "/private":
            return httpx.Response(403)
        if request.url.path == "/missing":
            return httpx.Response(404)
        return httpx.Response(204)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        checker = LinkChecker(
            settings(), client=client, dns_guard=DnsGuard(resolver=public_resolver)
        )
        results = await checker.check_all(
            [
                InputUrl(1, "https://example.com/redirect"),
                InputUrl(2, "https://example.com/private"),
                InputUrl(3, "https://example.com/missing"),
            ]
        )

    assert [result.state for result in results] == [
        LinkState.WORKING,
        LinkState.RESTRICTED,
        LinkState.BROKEN,
    ]
    assert [result.is_working for result in results] == [True, True, False]
    assert results[0].final_url == "https://example.com/ok"


@pytest.mark.asyncio
async def test_checker_only_requests_duplicate_once() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        checker = LinkChecker(
            settings(), client=client, dns_guard=DnsGuard(resolver=public_resolver)
        )
        results = await checker.check_all(
            [InputUrl(1, "https://example.com"), InputUrl(9, "https://example.com")]
        )

    assert calls == 1
    assert [result.line_number for result in results] == [1, 9]
