"""Module a — imports b (part of cycle)."""

from . import b


def shared_double(x):
    return x * 2


def use_shared(values):
    return [shared_double(v) for v in values]


def also_uses(xs):
    return shared_double(sum(xs))


def deep_nest(a, b, c):
    if a:
        if b:
            if c:
                return 1
    return 0


def leaf_pipeline(rows):
    return list(filter(None, map(str, rows)))


def _dust(x):
    return x
