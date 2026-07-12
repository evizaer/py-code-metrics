"""Module b — imports c (part of cycle)."""

from . import c


def from_b():
    return c.marker()
