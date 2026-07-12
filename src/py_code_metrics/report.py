"""JSON report serialization."""

from __future__ import annotations

import json
from typing import Any

from py_code_metrics.model import MetricsReport


def report_to_dict(report: MetricsReport) -> dict[str, Any]:
    return report.to_dict()


def report_to_json(report: MetricsReport, *, indent: int = 2) -> str:
    return json.dumps(report_to_dict(report), indent=indent, sort_keys=False) + "\n"
