import io
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime
from urllib.parse import urlsplit

import xlsxwriter
from xlsxwriter.format import Format
from xlsxwriter.worksheet import Worksheet

from link_checker.models import LinkResult, LinkState

_STATE_LABELS = {
    "working": "Публичный объект найден",
    "restricted_but_reachable": "Объект найден с ограничениями",
    "broken": "Username не найден",
    "timeout": "Тайм-аут Telegram",
    "invalid": "Неподдерживаемая t.me-ссылка",
    "blocked_for_security": "Ссылка заблокирована",
    "network_error": "Ошибка Telegram API",
}


def _write_link(worksheet: Worksheet, row: int, column: int, value: str) -> None:
    parsed = urlsplit(value)
    if parsed.scheme in {"http", "https"} and len(value) <= 2_079:
        result = worksheet.write_url(row, column, value, string=value)
        if result == 0:
            return
    worksheet.write_string(row, column, value)


def build_xlsx(
    results: Sequence[LinkResult],
    *,
    job_id: str,
    cycle: int,
    generated_at: datetime | None = None,
) -> bytes:
    """Create a Russian, filterable Excel report entirely in memory."""
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {"in_memory": True})
    workbook.set_properties(
        {
            "title": f"Отчёт мониторинга t.me {job_id}",
            "subject": "Результаты проверки публичных Telegram-объектов",
            "author": "Telegram Public Link Monitor",
        }
    )

    title_format = workbook.add_format(
        {"font_name": "Arial", "font_size": 14, "bold": True, "font_color": "#172B4D"}
    )
    context_format = workbook.add_format(
        {"font_name": "Arial", "font_size": 10, "italic": True, "font_color": "#5E6C84"}
    )
    header_format = workbook.add_format(
        {
            "font_name": "Arial",
            "font_size": 10,
            "bold": True,
            "font_color": "#FFFFFF",
            "bg_color": "#1F4E78",
            "align": "center",
            "valign": "vcenter",
            "border": 0,
        }
    )
    body_format = workbook.add_format(
        {"font_name": "Arial", "font_size": 10, "font_color": "#172B4D", "valign": "vcenter"}
    )
    integer_format = workbook.add_format(
        {
            "font_name": "Arial",
            "font_size": 10,
            "font_color": "#172B4D",
            "align": "right",
            "num_format": "#,##0",
        }
    )
    percent_format = workbook.add_format(
        {
            "font_name": "Arial",
            "font_size": 10,
            "font_color": "#172B4D",
            "align": "right",
            "num_format": "0.0%",
        }
    )
    good_format = workbook.add_format({"bg_color": "#E2F0D9", "font_color": "#375623"})
    warning_format = workbook.add_format({"bg_color": "#FFF2CC", "font_color": "#7F6000"})
    bad_format = workbook.add_format({"bg_color": "#FCE4D6", "font_color": "#9C0006"})

    counts = Counter(result.state.value for result in results)
    working = sum(result.is_working for result in results)
    failed = len(results) - working
    missing = counts.get(LinkState.BROKEN.value, 0)
    requires_attention = failed - missing
    created = generated_at or datetime.now(UTC)
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    created = created.astimezone(UTC)

    summary_sheet = workbook.add_worksheet("Сводка")
    summary_sheet.hide_gridlines(2)
    summary_sheet.set_tab_color("#1F4E78")
    summary_sheet.set_column("A:A", 34)
    summary_sheet.set_column("B:B", 16)
    summary_sheet.write("A2", "Отчёт мониторинга публичных t.me-ссылок", title_format)
    summary_sheet.write("A3", f"Задание: {job_id} · Цикл: {cycle}", context_format)
    summary_sheet.write("A4", f"Сформировано: {created:%d.%m.%Y %H:%M} UTC", context_format)
    summary_sheet.write_row("A6", ["Показатель", "Количество"], header_format)
    summary_rows: list[tuple[str, int | float, Format]] = [
        ("Проверено t.me-ссылок", len(results), integer_format),
        ("Публичных объектов найдено", working, integer_format),
        ("Username не найдены", missing, integer_format),
        ("Требуют внимания", requires_attention, integer_format),
        ("Доля найденных объектов", working / len(results) if results else 0, percent_format),
    ]
    for row, (label, value, value_format) in enumerate(summary_rows, start=6):
        summary_sheet.write(row, 0, label, body_format)
        summary_sheet.write(row, 1, value, value_format)

    summary_sheet.write_row("A15", ["Статус", "Количество"], header_format)
    for row, state in enumerate(_STATE_LABELS, start=15):
        summary_sheet.write(row, 0, _STATE_LABELS[state], body_format)
        summary_sheet.write(row, 1, counts.get(state, 0), integer_format)
    summary_sheet.conditional_format("A16:A17", {"type": "no_blanks", "format": good_format})
    summary_sheet.conditional_format("A18:A22", {"type": "no_blanks", "format": bad_format})

    results_sheet = workbook.add_worksheet("Результаты")
    results_sheet.hide_gridlines(2)
    results_sheet.freeze_panes(1, 2)
    results_sheet.set_column("A:A", 10)
    results_sheet.set_column("B:B", 52)
    results_sheet.set_column("C:C", 12)
    results_sheet.set_column("D:D", 31)
    results_sheet.set_column("E:E", 12)
    results_sheet.set_column("F:F", 15)
    results_sheet.set_column("G:G", 52)
    results_sheet.set_column("H:H", 40)
    results_sheet.set_column("I:I", 16)

    headers = [
        "Строка",
        "t.me-ссылка",
        "Объект найден",
        "Результат",
        "Telegram ID",
        "Время, мс",
        "Публичный username",
        "Причина",
        "Тип объекта",
    ]
    results_sheet.write_row(0, 0, headers, header_format)
    for row, result in enumerate(results, start=1):
        results_sheet.write_number(row, 0, result.line_number, integer_format)
        _write_link(results_sheet, row, 1, result.url)
        results_sheet.write_string(row, 2, "Да" if result.is_working else "Нет", body_format)
        results_sheet.write_string(row, 3, _STATE_LABELS[result.state.value], body_format)
        if result.entity_id is not None:
            results_sheet.write_number(row, 4, result.entity_id, integer_format)
        if result.latency_ms is not None:
            results_sheet.write_number(row, 5, result.latency_ms, integer_format)
        if result.final_url:
            _write_link(results_sheet, row, 6, result.final_url)
        if result.error:
            results_sheet.write_string(row, 7, result.error, body_format)
        if result.entity_type:
            results_sheet.write_string(row, 8, result.entity_type, body_format)

    last_row = max(1, len(results))
    results_sheet.add_table(
        0,
        0,
        last_row,
        len(headers) - 1,
        {
            "name": "LinkResults",
            "style": "Table Style Medium 2",
            "columns": [{"header": header} for header in headers],
        },
    )
    if results:
        results_sheet.conditional_format(
            1,
            2,
            len(results),
            2,
            {"type": "text", "criteria": "containing", "value": "Да", "format": good_format},
        )
        results_sheet.conditional_format(
            1,
            2,
            len(results),
            2,
            {"type": "text", "criteria": "containing", "value": "Нет", "format": bad_format},
        )
        results_sheet.conditional_format(
            1,
            3,
            len(results),
            3,
            {
                "type": "text",
                "criteria": "containing",
                "value": "ограничениями",
                "format": warning_format,
            },
        )
        results_sheet.conditional_format(
            1,
            0,
            len(results),
            len(headers) - 1,
            {
                "type": "formula",
                "criteria": '=$D2="Username не найден"',
                "format": bad_format,
            },
        )

    def write_filtered_sheet(
        name: str,
        sheet_results: Sequence[LinkResult],
        *,
        tab_color: str,
    ) -> None:
        sheet = workbook.add_worksheet(name)
        sheet.hide_gridlines(2)
        sheet.set_tab_color(tab_color)
        sheet.freeze_panes(1, 2)
        sheet.set_column("A:A", 10)
        sheet.set_column("B:B", 52)
        sheet.set_column("C:C", 16)
        sheet.set_column("D:D", 31)
        sheet.set_column("E:E", 16)
        sheet.set_column("F:F", 15)
        sheet.set_column("G:G", 52)
        sheet.set_column("H:H", 40)
        sheet.set_column("I:I", 16)
        sheet.write_row(0, 0, headers, header_format)

        for row, result in enumerate(sheet_results, start=1):
            sheet.write_number(row, 0, result.line_number, integer_format)
            _write_link(sheet, row, 1, result.url)
            sheet.write_string(row, 2, "Да" if result.is_working else "Нет", body_format)
            sheet.write_string(row, 3, _STATE_LABELS[result.state.value], body_format)
            if result.entity_id is not None:
                sheet.write_number(row, 4, result.entity_id, integer_format)
            if result.latency_ms is not None:
                sheet.write_number(row, 5, result.latency_ms, integer_format)
            if result.final_url:
                _write_link(sheet, row, 6, result.final_url)
            if result.error:
                sheet.write_string(row, 7, result.error, body_format)
            if result.entity_type:
                sheet.write_string(row, 8, result.entity_type, body_format)

        if sheet_results:
            sheet.add_table(
                0,
                0,
                len(sheet_results),
                len(headers) - 1,
                {
                    "name": "FoundTelegramEntities"
                    if name == "Найдены"
                    else "MissingTelegramUsernames",
                    "style": "Table Style Medium 2",
                    "columns": [{"header": header} for header in headers],
                },
            )
            if name == "Username не найдены":
                sheet.conditional_format(
                    1,
                    0,
                    len(sheet_results),
                    len(headers) - 1,
                    {
                        "type": "formula",
                        "criteria": '=$D2="Username не найден"',
                        "format": bad_format,
                    },
                )

    write_filtered_sheet(
        "Найдены",
        [result for result in results if result.is_working],
        tab_color="#70AD47",
    )
    write_filtered_sheet(
        "Username не найдены",
        [result for result in results if result.state is LinkState.BROKEN],
        tab_color="#C00000",
    )

    workbook.close()
    return output.getvalue()


def summarize(results: Sequence[LinkResult]) -> str:
    counts = Counter(result.state.value for result in results)
    working = sum(result.is_working for result in results)
    details = ", ".join(f"{name}: {count}" for name, count in sorted(counts.items()))
    failed = len(results) - working
    return f"Checked {len(results):,}: {working:,} working, {failed:,} failed. {details}"


def summarize_ru(results: Sequence[LinkResult]) -> str:
    labels = {
        "working": "объекты найдены",
        "restricted_but_reachable": "объекты найдены с ограничениями",
        "broken": "username не найдены",
        "timeout": "тайм-аут Telegram",
        "invalid": "неподдерживаемые ссылки",
        "blocked_for_security": "ссылки заблокированы",
        "network_error": "ошибка Telegram API",
    }
    counts = Counter(result.state.value for result in results)
    working = sum(result.is_working for result in results)
    failed = len(results) - working
    details = ", ".join(
        f"{labels.get(name, name)}: {count}" for name, count in sorted(counts.items())
    )
    return (
        f"Проверено t.me-ссылок: {len(results):,}; объектов найдено: {working:,}; "
        f"не найдены или не проверены: {failed:,}. {details}"
    )
