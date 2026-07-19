"""Kitchen-sink public surface with tiny bodies (classitis / high PIW)."""


class A:
    def run(self, x: int) -> int:
        return x


class B:
    def run(self, x: int) -> int:
        return x


class C:
    def run(self, x: int) -> int:
        return x


def f1(a: int) -> int:
    return a


def f2(a: int, b: int) -> int:
    return a + b


def f3(a: int, b: int, c: int) -> int:
    return a + b + c
