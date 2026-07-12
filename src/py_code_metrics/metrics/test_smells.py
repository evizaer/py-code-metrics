"""Smell codes and severity for static fake-test detection."""

from __future__ import annotations

from typing import Literal

from py_code_metrics.metrics.test_oracles import (
    EXEMPT_MARKERS,
    TestFunctionInfo,
    classify_oracle_tier,
    oracle_kinds,
)

Severity = Literal["high", "low", "info"]

# Catalog-aligned codes (falsegreen / rotten-green families).
SMELL_NO_ORACLE = "NO_ORACLE"
SMELL_TAUTOLOGY = "TAUTOLOGY"
SMELL_WEAK_ORACLE = "WEAK_ORACLE"
SMELL_SWALLOWED_ERROR = "SWALLOWED_ERROR"
SMELL_SKIP_IN_EXCEPT = "SKIP_IN_EXCEPT"
SMELL_EMPTY_BODY = "EMPTY_BODY"


def derive_smells(info: TestFunctionInfo) -> tuple[list[str], Severity, bool]:
    """Return (smell_codes, severity, exempt) for a test function."""
    exempt = _is_exempt(info)
    codes: list[str] = []
    tier = classify_oracle_tier(info.oracles)

    if info.empty_body:
        codes.append(SMELL_EMPTY_BODY)
    if any(o.strength == "tautology" for o in info.oracles):
        codes.append(SMELL_TAUTOLOGY)
    if info.has_swallowed_error:
        codes.append(SMELL_SWALLOWED_ERROR)
    if info.has_skip_in_except:
        codes.append(SMELL_SKIP_IN_EXCEPT)

    real_oracles = [o for o in info.oracles if o.strength != "tautology"]
    if not real_oracles and not info.allow_no_oracle:
        if SMELL_NO_ORACLE not in codes:
            codes.append(SMELL_NO_ORACLE)
    elif tier == "weak":
        codes.append(SMELL_WEAK_ORACLE)

    severity = _severity_for(codes, exempt=exempt)
    if exempt:
        # Keep codes for visibility but demote severity.
        severity = "info"
    return codes, severity, exempt


def _is_exempt(info: TestFunctionInfo) -> bool:
    if info.allow_no_oracle:
        return True
    marks = {m.lower() for m in info.markers}
    return bool(marks & {m.lower() for m in EXEMPT_MARKERS})


def _severity_for(codes: list[str], *, exempt: bool) -> Severity:
    if exempt:
        return "info"
    high = {
        SMELL_NO_ORACLE,
        SMELL_TAUTOLOGY,
        SMELL_SWALLOWED_ERROR,
        SMELL_EMPTY_BODY,
        SMELL_SKIP_IN_EXCEPT,
    }
    if any(c in high for c in codes):
        return "high"
    if SMELL_WEAK_ORACLE in codes:
        return "low"
    return "info"


def assertion_count(info: TestFunctionInfo) -> int:
    """Count non-tautology oracles (asserts, raises, mock asserts, …)."""
    return sum(1 for o in info.oracles if o.strength != "tautology")


def summarize_oracles(info: TestFunctionInfo) -> tuple[str, list[str], int]:
    tier = classify_oracle_tier(info.oracles)
    kinds = oracle_kinds([o for o in info.oracles if o.strength != "tautology"])
    # Keep tautology visible in kinds when present
    if any(o.strength == "tautology" for o in info.oracles) and "tautology" not in kinds:
        kinds = [*kinds, "tautology"]
    return tier, kinds, assertion_count(info)
