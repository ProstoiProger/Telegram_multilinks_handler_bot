from dataclasses import dataclass


class InputError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class InputUrl:
    line_number: int
    url: str


def parse_url_file(data: bytes, *, max_urls: int) -> list[InputUrl]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise InputError("The file must be UTF-8 encoded.") from exc

    urls: list[InputUrl] = []
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        value = raw_line.strip()
        if not value or value.startswith("#"):
            continue
        urls.append(InputUrl(line_number=line_number, url=value))
        if len(urls) > max_urls:
            raise InputError(f"The file contains more than {max_urls:,} non-empty lines.")

    if not urls:
        raise InputError("The file does not contain any links.")
    return urls

