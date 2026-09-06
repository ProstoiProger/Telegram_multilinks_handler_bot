import asyncio
import time
from collections.abc import Sequence
from urllib.parse import urljoin

import httpx

from link_checker.config import Settings
from link_checker.models import LinkResult, LinkState
from link_checker.parser import InputUrl
from link_checker.security import DnsGuard, DnsResolutionError, InvalidUrlError, UnsafeUrlError

_RESTRICTED_BUT_REACHABLE = {401, 403, 405, 407, 423, 429, 451}
_REDIRECTS = {301, 302, 303, 307, 308}


class LinkChecker:
    def __init__(
        self,
        settings: Settings,
        *,
        client: httpx.AsyncClient | None = None,
        dns_guard: DnsGuard | None = None,
    ) -> None:
        self.settings = settings
        self._external_client = client
        self.dns_guard = dns_guard or DnsGuard()

    async def check_all(self, urls: Sequence[InputUrl]) -> list[LinkResult]:
        unique: dict[str, InputUrl] = {}
        for item in urls:
            unique.setdefault(item.url, item)

        semaphore = asyncio.Semaphore(self.settings.check_concurrency)
        if self._external_client is not None:
            checked = await self._run_unique(
                list(unique.values()), self._external_client, semaphore
            )
        else:
            timeout = httpx.Timeout(
                connect=self.settings.check_connect_timeout_seconds,
                read=self.settings.check_read_timeout_seconds,
                write=self.settings.check_connect_timeout_seconds,
                pool=self.settings.check_connect_timeout_seconds,
            )
            limits = httpx.Limits(
                max_connections=self.settings.check_concurrency,
                max_keepalive_connections=min(100, self.settings.check_concurrency),
                keepalive_expiry=15.0,
            )
            async with httpx.AsyncClient(
                timeout=timeout,
                limits=limits,
                http2=self.settings.check_http2,
                follow_redirects=False,
                trust_env=False,
                headers={
                    "User-Agent": "LinkHealthBot/1.0 (+https://core.telegram.org/bots)",
                    "Accept": "*/*",
                },
            ) as client:
                checked = await self._run_unique(list(unique.values()), client, semaphore)

        by_url = {result.url: result for result in checked}
        return [by_url[item.url].for_occurrence(item.line_number, item.url) for item in urls]

    async def _run_unique(
        self,
        urls: list[InputUrl],
        client: httpx.AsyncClient,
        semaphore: asyncio.Semaphore,
    ) -> list[LinkResult]:
        async def bounded(item: InputUrl) -> LinkResult:
            async with semaphore:
                return await self._check_with_deadline(item, client)

        return list(await asyncio.gather(*(bounded(item) for item in urls)))

    async def _check_with_deadline(
        self, item: InputUrl, client: httpx.AsyncClient
    ) -> LinkResult:
        started = time.perf_counter()
        try:
            async with asyncio.timeout(self.settings.check_total_timeout_seconds):
                return await self._check_with_retries(item, client, started)
        except TimeoutError:
            return self._failure(item, LinkState.TIMEOUT, started, "total timeout exceeded")

    async def _check_with_retries(
        self,
        item: InputUrl,
        client: httpx.AsyncClient,
        started: float,
    ) -> LinkResult:
        attempts = self.settings.check_retries + 1
        last_result: LinkResult | None = None
        for attempt in range(attempts):
            last_result = await self._check_once(item, client, started)
            if last_result.state not in {LinkState.TIMEOUT, LinkState.NETWORK_ERROR}:
                return last_result
            if attempt + 1 < attempts:
                await asyncio.sleep(0.05 * (2**attempt))
        assert last_result is not None
        return last_result

    async def _check_once(
        self,
        item: InputUrl,
        client: httpx.AsyncClient,
        started: float,
    ) -> LinkResult:
        current = item.url
        try:
            for redirect_number in range(self.settings.check_max_redirects + 1):
                current = await self.dns_guard.validate(current)
                async with client.stream("GET", current) as response:
                    status = response.status_code
                    location = response.headers.get("location")

                if status in _REDIRECTS and location:
                    if redirect_number >= self.settings.check_max_redirects:
                        return self._failure(
                            item,
                            LinkState.BROKEN,
                            started,
                            "too many redirects",
                            status_code=status,
                            final_url=current,
                        )
                    current = urljoin(current, location)
                    continue
                return self._from_status(item, status, started, current)
        except InvalidUrlError as exc:
            return self._failure(item, LinkState.INVALID, started, str(exc), final_url=current)
        except UnsafeUrlError as exc:
            return self._failure(item, LinkState.BLOCKED, started, str(exc), final_url=current)
        except DnsResolutionError as exc:
            return self._failure(
                item, LinkState.NETWORK_ERROR, started, str(exc), final_url=current
            )
        except httpx.TimeoutException as exc:
            return self._failure(item, LinkState.TIMEOUT, started, type(exc).__name__, current)
        except (httpx.NetworkError, httpx.ProtocolError) as exc:
            return self._failure(
                item, LinkState.NETWORK_ERROR, started, type(exc).__name__, final_url=current
            )
        except httpx.HTTPError as exc:
            return self._failure(item, LinkState.BROKEN, started, type(exc).__name__, current)
        except ValueError as exc:
            return self._failure(item, LinkState.INVALID, started, str(exc), current)
        except Exception as exc:
            return self._failure(
                item, LinkState.NETWORK_ERROR, started, type(exc).__name__, current
            )

        return self._failure(item, LinkState.BROKEN, started, "unexpected redirect state", current)

    def _from_status(
        self, item: InputUrl, status: int, started: float, final_url: str
    ) -> LinkResult:
        if 200 <= status < 400:
            state, working = LinkState.WORKING, True
        elif status in _RESTRICTED_BUT_REACHABLE:
            state, working = LinkState.RESTRICTED, True
        else:
            state, working = LinkState.BROKEN, False
        return LinkResult(
            line_number=item.line_number,
            url=item.url,
            is_working=working,
            state=state,
            status_code=status,
            latency_ms=self._elapsed_ms(started),
            final_url=final_url,
        )

    @staticmethod
    def _failure(
        item: InputUrl,
        state: LinkState,
        started: float,
        error: str,
        final_url: str | None = None,
        status_code: int | None = None,
    ) -> LinkResult:
        return LinkResult(
            line_number=item.line_number,
            url=item.url,
            is_working=False,
            state=state,
            status_code=status_code,
            latency_ms=LinkChecker._elapsed_ms(started),
            final_url=final_url,
            error=error,
        )

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        return round((time.perf_counter() - started) * 1000)
