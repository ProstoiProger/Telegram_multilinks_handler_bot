import re
from urllib.parse import urlsplit

from link_checker.security import InvalidUrlError

_HOSTS = {"t.me", "www.t.me", "telegram.me", "www.telegram.me"}
_USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{4,31}$")


def extract_public_username(raw_url: str) -> str:
    """Extract an entity username from a public t.me link.

    Invite links, private-channel links and service links are intentionally excluded:
    they cannot establish that a public user, bot, channel or group exists.
    """
    try:
        parts = urlsplit(raw_url)
    except ValueError as exc:
        raise InvalidUrlError("invalid Telegram link") from exc

    if parts.scheme.lower() not in {"http", "https"} or parts.hostname not in _HOSTS:
        raise InvalidUrlError("only public http(s) t.me links are allowed")

    path = [segment for segment in parts.path.split("/") if segment]
    if path[:1] == ["s"]:
        path = path[1:]
    if not path:
        raise InvalidUrlError("Telegram link has no public username")

    username = path[0]
    if username.lower() in {
        "joinchat", "addstickers", "addemoji", "share", "iv", "proxy", "login", "boost", "c",
    } or username.startswith("+"):
        raise InvalidUrlError("private or service Telegram links are not supported")
    if not _USERNAME_RE.fullmatch(username):
        raise InvalidUrlError("Telegram username has an invalid format")
    return username.lower()
