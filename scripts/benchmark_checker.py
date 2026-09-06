"""Measure checker orchestration overhead without pretending to benchmark the internet."""

import asyncio
import socket
import time

import httpx

from link_checker.checker import LinkChecker
from link_checker.config import Settings
from link_checker.parser import InputUrl
from link_checker.security import DnsGuard


async def public_resolver(host: str, port: int) -> list[tuple[object, ...]]:
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]


async def main() -> None:
    count = 1_000
    urls = [InputUrl(i + 1, f"https://example.com/{i}") for i in range(count)]
    settings = Settings(bot_token="123456:benchmark", check_concurrency=300)
    transport = httpx.MockTransport(lambda request: httpx.Response(204))
    started = time.perf_counter()
    async with httpx.AsyncClient(transport=transport) as client:
        results = await LinkChecker(
            settings, client=client, dns_guard=DnsGuard(resolver=public_resolver)
        ).check_all(urls)
    elapsed = time.perf_counter() - started
    assert len(results) == count
    print(f"Checked {count} mocked URLs in {elapsed:.3f}s ({count / elapsed:,.0f} URLs/s)")


if __name__ == "__main__":
    asyncio.run(main())

