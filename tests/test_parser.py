import pytest

from link_checker.parser import InputError, parse_url_file


def test_parse_ignores_blanks_comments_and_utf8_bom() -> None:
    parsed = parse_url_file(
        b"\xef\xbb\xbf# websites\nhttps://example.com\n\n http://example.org/path \n",
        max_urls=10,
    )
    assert [(item.line_number, item.url) for item in parsed] == [
        (2, "https://example.com"),
        (4, "http://example.org/path"),
    ]


def test_parse_enforces_limit() -> None:
    with pytest.raises(InputError, match="more than 1"):
        parse_url_file(b"https://one.test\nhttps://two.test", max_urls=1)

