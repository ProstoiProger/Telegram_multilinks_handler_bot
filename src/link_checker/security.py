import asyncio
import ipaddress
import socket
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, cast
from urllib.parse import SplitResult, urlsplit, urlunsplit


class UnsafeUrlError(ValueError):
    pass


class InvalidUrlError(ValueError):
    pass


class DnsResolutionError(OSError):
    pass


AddrInfo = tuple[Any, ...]
Resolver = Callable[[str, int], Awaitable[list[AddrInfo]]]


async def _default_resolver(host: str, port: int) -> list[AddrInfo]:
    loop = asyncio.get_running_loop()
    result = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return cast(list[AddrInfo], result)


def _is_public_ip(value: str) -> bool:
    try:
        return ipaddress.ip_address(value).is_global
    except ValueError:
        return False


def _normalized_parts(raw_url: str) -> SplitResult:
    if len(raw_url) > 8_192:
        raise InvalidUrlError("URL is longer than 8,192 characters")
    try:
        parts = urlsplit(raw_url)
        port = parts.port
    except ValueError as exc:
        raise InvalidUrlError("URL has an invalid host or port") from exc

    if parts.scheme.lower() not in {"http", "https"}:
        raise InvalidUrlError("only http:// and https:// URLs are allowed")
    if not parts.hostname:
        raise InvalidUrlError("URL has no hostname")
    if parts.username is not None or parts.password is not None:
        raise InvalidUrlError("credentials in URLs are not allowed")
    if port is not None and not 1 <= port <= 65_535:
        raise InvalidUrlError("URL has an invalid port")
    return parts


@dataclass(slots=True)
class DnsGuard:
    """Best-effort SSRF guard. Production should also enforce an egress firewall."""

    resolver: Resolver = _default_resolver
    cache_ttl_seconds: float = 30.0
    _cache: dict[tuple[str, int], tuple[float, tuple[str, ...]]] = field(default_factory=dict)
    _locks: dict[tuple[str, int], asyncio.Lock] = field(default_factory=dict)

    async def validate(self, raw_url: str) -> str:
        parts = _normalized_parts(raw_url)
        host = parts.hostname
        assert host is not None
        try:
            host_ascii = host.encode("idna").decode("ascii").lower().rstrip(".")
        except UnicodeError as exc:
            raise InvalidUrlError("hostname is not valid IDNA") from exc

        if host_ascii in {"localhost", "localhost.localdomain"} or host_ascii.endswith(
            (".localhost", ".local", ".internal")
        ):
            raise UnsafeUrlError("local hostnames are blocked")

        try:
            literal = ipaddress.ip_address(host_ascii.strip("[]"))
        except ValueError:
            literal = None
        if literal is not None and not literal.is_global:
            raise UnsafeUrlError("non-public IP addresses are blocked")

        port = parts.port or (443 if parts.scheme.lower() == "https" else 80)
        addresses = await self._resolve(host_ascii, port)
        if any(not _is_public_ip(address) for address in addresses):
            raise UnsafeUrlError("hostname resolves to a non-public IP address")

        netloc = host_ascii
        if ":" in host_ascii and not host_ascii.startswith("["):
            netloc = f"[{host_ascii}]"
        if parts.port is not None:
            netloc = f"{netloc}:{parts.port}"
        path = parts.path or "/"
        return urlunsplit((parts.scheme.lower(), netloc, path, parts.query, ""))

    async def _resolve(self, host: str, port: int) -> tuple[str, ...]:
        key = (host, port)
        now = time.monotonic()
        cached = self._cache.get(key)
        if cached is not None and cached[0] > now:
            return cached[1]

        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            cached = self._cache.get(key)
            if cached is not None and cached[0] > time.monotonic():
                return cached[1]
            try:
                records = await self.resolver(host, port)
            except (OSError, UnicodeError) as exc:
                raise DnsResolutionError(f"DNS lookup failed: {type(exc).__name__}") from exc
            addresses = tuple({str(record[4][0]) for record in records})
            if not addresses:
                raise DnsResolutionError("hostname did not resolve")
            self._cache[key] = (time.monotonic() + self.cache_ttl_seconds, addresses)
            return addresses
