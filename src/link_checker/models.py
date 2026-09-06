from dataclasses import dataclass, replace
from enum import StrEnum


class LinkState(StrEnum):
    WORKING = "working"
    RESTRICTED = "restricted_but_reachable"
    BROKEN = "broken"
    TIMEOUT = "timeout"
    INVALID = "invalid"
    BLOCKED = "blocked_for_security"
    NETWORK_ERROR = "network_error"


@dataclass(frozen=True, slots=True)
class LinkResult:
    line_number: int
    url: str
    is_working: bool
    state: LinkState
    status_code: int | None = None
    latency_ms: int | None = None
    final_url: str | None = None
    error: str | None = None

    def for_occurrence(self, line_number: int, url: str) -> "LinkResult":
        return replace(self, line_number=line_number, url=url)

