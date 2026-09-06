import csv
import io
from collections import Counter
from collections.abc import Sequence

from link_checker.models import LinkResult


def build_csv(results: Sequence[LinkResult]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(
        [
            "line",
            "url",
            "working",
            "state",
            "http_status",
            "latency_ms",
            "final_url",
            "error",
        ]
    )
    for result in results:
        writer.writerow(
            [
                result.line_number,
                result.url,
                str(result.is_working).lower(),
                result.state.value,
                result.status_code or "",
                result.latency_ms if result.latency_ms is not None else "",
                result.final_url or "",
                result.error or "",
            ]
        )
    return output.getvalue().encode("utf-8-sig")


def summarize(results: Sequence[LinkResult]) -> str:
    counts = Counter(result.state.value for result in results)
    working = sum(result.is_working for result in results)
    details = ", ".join(f"{name}: {count}" for name, count in sorted(counts.items()))
    failed = len(results) - working
    return f"Checked {len(results):,}: {working:,} working, {failed:,} failed. {details}"


def summarize_ru(results: Sequence[LinkResult]) -> str:
    labels = {
        "working": "доступны",
        "restricted_but_reachable": "доступны с ограничениями",
        "broken": "не работают",
        "timeout": "тайм-аут",
        "invalid": "некорректны",
        "blocked_for_security": "заблокированы безопасностью",
        "network_error": "ошибка сети",
    }
    counts = Counter(result.state.value for result in results)
    working = sum(result.is_working for result in results)
    failed = len(results) - working
    details = ", ".join(
        f"{labels.get(name, name)}: {count}" for name, count in sorted(counts.items())
    )
    return (
        f"Проверено: {len(results):,}; доступны: {working:,}; "
        f"недоступны: {failed:,}. {details}"
    )
