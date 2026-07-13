"""Stateful production types for state-field coverage fixtures."""

from __future__ import annotations


class Counter:
    def __init__(self, value: int = 0) -> None:
        self.value = value
        self.history: list[int] = []

    def inc(self) -> int:
        self.value += 1
        self.history.append(self.value)
        return self.value

    def snapshot(self) -> int:
        return self.value


class Node:
    def __init__(self, item: int, next: Node | None = None) -> None:
        self.item = item
        self.next = next
