from link_checker.models import LinkResult, LinkState
from link_checker.reporting import build_csv, summarize, summarize_ru


def test_report_contains_bom_and_summary() -> None:
    results = [
        LinkResult(1, "https://example.com", True, LinkState.WORKING, status_code=200),
        LinkResult(2, "https://missing.test", False, LinkState.BROKEN, status_code=404),
    ]
    report = build_csv(results)
    assert report.startswith(b"\xef\xbb\xbf")
    assert b"https://example.com" in report
    assert "1 working, 1 failed" in summarize(results)
    assert "доступны: 1" in summarize_ru(results)
