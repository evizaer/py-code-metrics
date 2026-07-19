"""Deep library core — few public exports, substantial private work."""


def open_stream(path: str) -> bytes:
    data = _read_all(path)
    return _decode(data)


def _read_all(path: str) -> bytes:
    # Fake body mass for MDI (kept non-trivial for token count).
    chunks: list[bytes] = []
    for i in range(8):
        chunks.append(path.encode() + bytes([i % 256]))
    return b"".join(chunks)


def _decode(data: bytes) -> bytes:
    out = bytearray()
    for b in data:
        out.append(b ^ 0x5A)
    return bytes(out)


def transform(x: int) -> int:
    y = _scale(x)
    return _clamp(y)


def _scale(x: int) -> int:
    return x * 3 + 1


def _clamp(x: int) -> int:
    if x < 0:
        return 0
    if x > 100:
        return 100
    return x
