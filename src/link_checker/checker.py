import asyncio
import time
from collections.abc import Sequence

from telethon import TelegramClient, errors
from telethon.sessions import MemorySession
from telethon.tl.types import Channel, Chat, User

from link_checker.config import Settings
from link_checker.models import LinkResult, LinkState
from link_checker.parser import InputUrl
from link_checker.security import InvalidUrlError
from link_checker.telegram_links import extract_public_username


class LinkChecker:
    """Resolve public Telegram usernames instead of making HTTP requests to t.me."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def check_all(self, urls: Sequence[InputUrl]) -> list[LinkResult]:
        unique: dict[str, InputUrl] = {}
        for item in urls:
            unique.setdefault(item.url, item)

        if (
            not self.settings.telegram_api_id
            or not self.settings.telegram_api_hash.get_secret_value()
        ):
            checked = [
                self._failure(
                    item,
                    LinkState.NETWORK_ERROR,
                    time.perf_counter(),
                    "TELEGRAM_API_ID and TELEGRAM_API_HASH are not configured",
                )
                for item in unique.values()
            ]
        else:
            checked = await self._resolve_unique(list(unique.values()))

        by_url = {result.url: result for result in checked}
        return [by_url[item.url].for_occurrence(item.line_number, item.url) for item in urls]

    async def _resolve_unique(self, urls: list[InputUrl]) -> list[LinkResult]:
        client = TelegramClient(
            MemorySession(),
            self.settings.telegram_api_id,
            self.settings.telegram_api_hash.get_secret_value(),
        )
        try:
            await client.start(bot_token=self.settings.bot_token.get_secret_value())
            semaphore = asyncio.Semaphore(self.settings.check_concurrency)

            async def bounded(item: InputUrl) -> LinkResult:
                async with semaphore:
                    return await self._check_one(item, client)

            return list(await asyncio.gather(*(bounded(item) for item in urls)))
        except (errors.RPCError, OSError, ConnectionError) as exc:
            started = time.perf_counter()
            return [
                self._failure(item, LinkState.NETWORK_ERROR, started, type(exc).__name__)
                for item in urls
            ]
        finally:
            await client.disconnect()

    async def _check_one(self, item: InputUrl, client: TelegramClient) -> LinkResult:
        started = time.perf_counter()
        try:
            username = extract_public_username(item.url)
            async with asyncio.timeout(self.settings.check_total_timeout_seconds):
                entity = await client.get_entity(username)
            return LinkResult(
                line_number=item.line_number,
                url=item.url,
                is_working=True,
                state=LinkState.WORKING,
                entity_id=self._entity_id(entity),
                latency_ms=self._elapsed_ms(started),
                final_url=f"https://t.me/{username}",
                entity_type=self._entity_type(entity),
            )
        except InvalidUrlError as exc:
            return self._failure(item, LinkState.INVALID, started, str(exc))
        except errors.UsernameNotOccupiedError:
            return self._failure(item, LinkState.BROKEN, started, "Telegram username not found")
        except errors.UsernameInvalidError:
            return self._failure(item, LinkState.INVALID, started, "Telegram username is invalid")
        except ValueError:
            return self._failure(item, LinkState.BROKEN, started, "Telegram username not found")
        except errors.FloodWaitError as exc:
            return self._failure(
                item, LinkState.TIMEOUT, started, f"Telegram flood wait: {exc.seconds}s"
            )
        except TimeoutError:
            return self._failure(item, LinkState.TIMEOUT, started, "Telegram request timed out")
        except (errors.RPCError, OSError, ConnectionError) as exc:
            return self._failure(item, LinkState.NETWORK_ERROR, started, type(exc).__name__)
        except Exception as exc:
            return self._failure(item, LinkState.NETWORK_ERROR, started, type(exc).__name__)

    @staticmethod
    def _entity_type(entity: object) -> str:
        if isinstance(entity, User):
            return "bot" if entity.bot else "user"
        if isinstance(entity, Channel):
            return "channel" if entity.broadcast else "group"
        if isinstance(entity, Chat):
            return "group"
        return type(entity).__name__.lower()

    @staticmethod
    def _entity_id(entity: object) -> int | None:
        if isinstance(entity, (User, Channel, Chat)):
            return entity.id
        return None

    @staticmethod
    def _failure(item: InputUrl, state: LinkState, started: float, error: str) -> LinkResult:
        return LinkResult(
            line_number=item.line_number,
            url=item.url,
            is_working=False,
            state=state,
            latency_ms=LinkChecker._elapsed_ms(started),
            error=error,
        )

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        return round((time.perf_counter() - started) * 1000)
