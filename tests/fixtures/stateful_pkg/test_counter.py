"""Tests exercising Counter state with varied oracle strength."""

from counter import Counter, Node


def test_inc_return_only():
    c = Counter(0)
    assert c.inc() == 1


def test_inc_checks_value():
    c = Counter(0)
    c.inc()
    assert c.value == 1


def test_inc_checks_history_loop():
    c = Counter(0)
    c.inc()
    c.inc()
    assert all(x > 0 for x in c.history)


def test_node_item_only():
    n = Node(3)
    assert n.item == 3


def test_snapshot_one_hop():
    c = Counter(4)
    assert c.snapshot() == 4
