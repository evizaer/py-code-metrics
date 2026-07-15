"""Annotation-driven dataclass ↔ dict conversion.

Convention
----------
- JSON key defaults to the field name.
- ``metadata={"key": "class"}`` renames (e.g. ``class_`` ↔ ``"class"``).
- ``metadata={"omit_none": True}`` drops ``None`` on write.
- ``metadata={"nest": "metrics"}`` groups fields under a nested object on the wire.
- Nested dataclasses, ``list[...]``, ``X | None``, and primitives coerce recursively.
- Missing keys use the field default / default_factory, else a type-empty value.
"""

from __future__ import annotations

from dataclasses import MISSING, fields, is_dataclass
from types import UnionType
from typing import Any, Literal, Union, get_args, get_origin, get_type_hints

_MISSING = object()

_EMPTY_PRIMITIVE: dict[Any, Any] = {
    int: 0,
    float: 0.0,
    bool: False,
    str: "",
}


def from_mapping(cls: type[Any], data: Any) -> Any:
    """Build a dataclass instance from a mapping (or ``{}`` if *data* is not a dict)."""
    if not is_dataclass(cls):
        raise TypeError(f"{cls!r} is not a dataclass")
    raw = data if isinstance(data, dict) else {}
    hints = get_type_hints(cls)
    kwargs: dict[str, Any] = {}
    for f in fields(cls):
        typ = hints.get(f.name, Any)
        wire = _read_wire(raw, f)
        if wire is _MISSING:
            if f.default is not MISSING:
                continue
            if f.default_factory is not MISSING:  # type: ignore[misc]
                continue
            kwargs[f.name] = _empty(typ)
        else:
            default = f.default if f.default is not MISSING else _empty(typ)
            kwargs[f.name] = coerce(wire, typ, default)
    return cls(**kwargs)


def to_mapping(obj: Any) -> dict[str, Any]:
    """Serialize a dataclass to a plain dict following the same conventions."""
    if not is_dataclass(obj) or isinstance(obj, type):
        raise TypeError(f"{obj!r} is not a dataclass instance")
    out: dict[str, Any] = {}
    nests: dict[str, dict[str, Any]] = {}
    for f in fields(obj):
        meta = f.metadata
        key = meta.get("key", f.name)
        nest = meta.get("nest")
        value = getattr(obj, f.name)
        if meta.get("omit_none") and value is None:
            continue
        serialized = serialize(value)
        if nest:
            nests.setdefault(nest, {})[key] = serialized
        else:
            out[key] = serialized
    out.update(nests)
    return out


def coerce(value: Any, typ: Any, default: Any = None) -> Any:
    """Coerce *value* toward *typ* (primitives, optionals, lists, nested dataclasses)."""
    if typ is Any:
        return value
    origin = get_origin(typ)
    if _is_union(origin):
        return _coerce_union(value, typ, default)
    if origin is Literal:
        return default if value is None else value
    if origin is list:
        return _coerce_list(value, typ, default)
    if is_dataclass(typ):
        return from_mapping(typ, value)
    return _primitive(typ, value, default)


def serialize(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        to_dict = getattr(value, "to_dict", None)
        if callable(to_dict):
            return to_dict()
        return to_mapping(value)
    if isinstance(value, list):
        return [serialize(item) for item in value]
    return value


class MappingMixin:
    """Drop-in ``to_dict`` / ``from_dict`` for dataclasses."""

    def to_dict(self) -> dict[str, Any]:
        return to_mapping(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Any:
        return from_mapping(cls, data)


def _read_wire(raw: dict[str, Any], f: Any) -> Any:
    meta = f.metadata
    key = meta.get("key", f.name)
    nest = meta.get("nest")
    if nest:
        nested = raw.get(nest)
        if isinstance(nested, dict) and key in nested:
            return nested[key]
        return _MISSING
    if key in raw:
        return raw[key]
    return _MISSING


def _is_union(origin: Any) -> bool:
    return origin is Union or origin is UnionType


def _non_none_args(typ: Any) -> list[Any]:
    return [a for a in get_args(typ) if a is not type(None)]


def _coerce_union(value: Any, typ: Any, default: Any) -> Any:
    if value is None:
        return None
    args = _non_none_args(typ)
    return coerce(value, args[0], default) if args else value


def _coerce_list(value: Any, typ: Any, default: Any) -> Any:
    elem = get_args(typ)[0] if get_args(typ) else Any
    if not isinstance(value, list):
        return [] if default is None else default
    return [coerce(item, elem, _empty(elem)) for item in value]


def _primitive(typ: Any, value: Any = _MISSING, default: Any = None) -> Any:
    """Empty default when *value* is omitted; otherwise coerce a scalar."""
    if value is _MISSING:
        return _EMPTY_PRIMITIVE.get(typ)
    if typ is int:
        return _as_int(value, default if isinstance(default, int) else 0)
    if typ is float:
        return _as_float(value, default if isinstance(default, float) else 0.0)
    if typ is bool:
        return (default if isinstance(default, bool) else False) if value is None else bool(value)
    if typ is str:
        return (default if isinstance(default, str) else "") if value is None else str(value)
    return value if value is not None else default


def _empty(typ: Any) -> Any:
    origin = get_origin(typ)
    if _is_union(origin):
        if type(None) in get_args(typ):
            return None
        args = _non_none_args(typ)
        return _empty(args[0]) if args else None
    if origin is list:
        return []
    if origin is Literal:
        args = get_args(typ)
        return args[0] if args else None
    if is_dataclass(typ):
        return from_mapping(typ, {})
    return _primitive(typ)


def _as_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
