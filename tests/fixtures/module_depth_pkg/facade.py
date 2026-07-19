"""Shallow pass-through façade — signature-echo wrappers."""

from . import deep_core


def open_stream(path: str) -> bytes:
    return deep_core.open_stream(path)


def transform(x: int) -> int:
    return deep_core.transform(x)
