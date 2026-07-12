"""Hotspot / paid-helper shapes for dashboard tests."""

from __future__ import annotations


def shared_branchy(x: int) -> str:
    """Reused helper with real branching — paid when F>=2."""
    if x < 0:
        return "neg"
    if x == 0:
        return "zero"
    if x == 1:
        return "one"
    if x == 2:
        return "two"
    if x == 3:
        return "three"
    if x == 4:
        return "four"
    if x == 5:
        return "five"
    if x < 10:
        return "small"
    if x < 20:
        return "mid"
    if x < 50:
        return "big"
    if x < 100:
        return "huge"
    return "max"


def use_a(x: int) -> str:
    return shared_branchy(x)


def use_b(x: int) -> str:
    return shared_branchy(x + 1)


def tangled_leaf(x: int, y: int) -> int:
    """Unpaid leaf with nesting — should appear as a hotspot."""
    total = 0
    if x > 0:
        if y > 0:
            if x > y:
                if x % 2 == 0:
                    total += x
                else:
                    total += y
            elif y % 2 == 0:
                total += y * 2
            else:
                total += x * 2
        elif y < -1:
            total -= y
        else:
            total += 1
    elif x < 0:
        if y:
            total = -x
        else:
            total = x
    else:
        total = y
    return total
