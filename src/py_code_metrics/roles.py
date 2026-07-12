"""Role classification: core / leaf / helper."""

from __future__ import annotations

from py_code_metrics.model import Role
from py_code_metrics.resolve import CallableInfo

CORE_FAN_IN_MIN = 3
ENTRYPOINT_NAMES = frozenset({"main", "run", "cli", "app"})


def classify_role(
    info: CallableInfo,
    *,
    fan_in_ext: int,
    call_count: int,
    assign_count: int,
) -> Role:
    """
    core: high external fan-in, not an obvious entrypoint.
    leaf: entrypoint / public module surface / low-F call-heavy orchestration.
    helper: private or unpaid low-reuse abstractions.
    """
    car = call_count / (1 + assign_count)
    is_entrypoint = info.name in ENTRYPOINT_NAMES or info.name.startswith("test_")
    is_dunder = info.name.startswith("__") and info.name.endswith("__")
    is_module_level = info.kind == "function" and info.parent_qname is None

    if fan_in_ext >= CORE_FAN_IN_MIN and not is_entrypoint:
        return "core"
    if is_entrypoint or is_dunder:
        return "leaf"
    if is_module_level and info.is_public:
        return "leaf"
    if fan_in_ext <= 1 and car >= 1.5:
        return "leaf"
    if fan_in_ext <= 1:
        return "helper"
    return "helper"
