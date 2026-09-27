import io
import zipfile

from link_checker.models import LinkResult, LinkState
from link_checker.reporting import build_xlsx, summarize, summarize_ru


def test_report_is_xlsx_with_russian_sheets_and_links() -> None:
    results = [
        LinkResult(1, "https://example.com", True, LinkState.WORKING, status_code=200),
        LinkResult(2, "https://missing.test", False, LinkState.BROKEN, status_code=404),
    ]
    report = build_xlsx(results, job_id="test-job", cycle=1)
    assert report.startswith(b"PK")
    with zipfile.ZipFile(io.BytesIO(report)) as archive:
        workbook_xml = archive.read("xl/workbook.xml").decode("utf-8")
        strings_xml = archive.read("xl/sharedStrings.xml").decode("utf-8")
    assert "Сводка" in workbook_xml
    assert "Результаты" in workbook_xml
    assert "Найдены" in workbook_xml
    assert "Username не найдены" in workbook_xml
    assert "https://example.com" in strings_xml
    assert "Username не найден" in strings_xml
    assert "1 working, 1 failed" in summarize(results)
    assert "объектов найдено: 1" in summarize_ru(results)
