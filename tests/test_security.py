import socket

import pytest

from link_checker.security import DnsGuard, InvalidUrlError, UnsafeUrlError


async def public_resolver(host: str, port: int) -> list[tuple[object, ...]]:
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]


@pytest.mark.asyncio
async def test_guard_normalizes_public_url() -> None:
    guard = DnsGuard(resolver=public_resolver)
    assert await guard.validate("HTTPS://Example.COM?q=1#fragment") == "https://example.com/?q=1"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://localhost/admin",
        "http://127.0.0.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://user:pass@example.com/",
    ],
)
async def test_guard_blocks_unsafe_targets(url: str) -> None:
    guard = DnsGuard(resolver=public_resolver)
    with pytest.raises((InvalidUrlError, UnsafeUrlError)):
        await guard.validate(url)
