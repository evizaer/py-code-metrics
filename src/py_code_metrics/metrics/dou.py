"""Dict-overuse (DOU): L1 untyped structured-mapping annotations."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field

from py_code_metrics.model import DouImpact, DouSite
from py_code_metrics.resolve import CallableInfo, SymbolIndex

DICT_OUTER = frozenset({"dict", "Dict", "Mapping", "MutableMapping"})
LIST_OUTER = frozenset({"list", "List", "Sequence", "MutableSequence"})
LOOSE_VALUE = frozenset({"Any", "object", "Object"})
STR_KEY = frozenset({"str", "Any"})
COERCE_ATTRS = frozenset({"from_dict", "model_validate", "model_validate_json", "parse_obj"})
RECORD_DECORATORS = frozenset({"dataclass", "define", "attrs", "frozen"})
RECORD_BASE_SUFFIXES = frozenset({"BaseModel", "BaseSettings", "Struct", "NamedTuple", "TypedDict"})


@dataclass
class DouResult:
    sites: list[DouSite] = field(default_factory=list)

    @property
    def n_sites(self) -> int:
        return len(self.sites)


def analyze_dou(
    info: CallableInfo,
    *,
    index: SymbolIndex,
    fan_in_ext: int,
    caller_modules: set[str],
) -> DouResult:
    """Flag L1 record annotations on params and returns; skip wire-then-coerce."""
    node = info.node
    sites: list[DouSite] = []
    public = _on_public_api(info)
    cross = _cross_module(info.module, caller_modules)
    impact_base = DouImpact(
        fan_out_sites=fan_in_ext,
        cross_module=cross,
        on_public_api=public,
    )

    for arg in _iter_params(node):
        if arg.annotation is None:
            continue
        if not is_loose_structured_annotation(arg.annotation):
            continue
        if _wire_coerce_exempt(node, arg.arg, index):
            continue
        ann = _ann_text(arg.annotation)
        impact = DouImpact(
            fan_out_sites=impact_base.fan_out_sites,
            key_vocab_size=_key_vocab_for_name(node, arg.arg),
            cross_module=impact_base.cross_module,
            on_public_api=impact_base.on_public_api,
        )
        sites.append(
            DouSite(
                dou_kind="record_annotation",
                site="param",
                name=arg.arg,
                annotation=ann,
                impact=impact,
            )
        )

    if (
        node.returns is not None
        and is_loose_structured_annotation(node.returns)
        and not _return_is_coerced_record(node, index)
    ):
        sites.append(
            DouSite(
                dou_kind="record_annotation",
                site="return",
                name=None,
                annotation=_ann_text(node.returns),
                impact=DouImpact(
                    fan_out_sites=impact_base.fan_out_sites,
                    key_vocab_size=_key_vocab_in_returns(node),
                    cross_module=impact_base.cross_module,
                    on_public_api=impact_base.on_public_api,
                ),
            )
        )

    return DouResult(sites=sites)


def is_loose_structured_annotation(node: ast.expr) -> bool:
    """True for dict/Mapping bags and list-of-bags with untyped values."""
    core = _unwrap_optional(node)
    if core is None:
        return False
    if isinstance(core, ast.Name) and core.id in DICT_OUTER:
        return True
    if not isinstance(core, ast.Subscript):
        return False
    outer = _simple_name(core.value)
    if outer in DICT_OUTER:
        return _dict_is_loose(core)
    if outer in LIST_OUTER:
        inner = _subscript_slice(core)
        return inner is not None and is_loose_structured_annotation(inner)
    return False


def _dict_is_loose(node: ast.Subscript) -> bool:
    sl = _subscript_slice(node)
    if sl is None:
        return True
    if isinstance(sl, ast.Tuple) and len(sl.elts) >= 2:
        key, val = sl.elts[0], sl.elts[1]
        if not _is_str_like_key(key):
            return False
        return _is_loose_value(val)
    # PEP 637 single-arg or unusual forms: treat as untyped bag
    return True


def _is_str_like_key(node: ast.expr) -> bool:
    name = _simple_name(_unwrap_optional(node) or node)
    return name in STR_KEY or name is None


def _is_loose_value(node: ast.expr) -> bool:
    core = _unwrap_optional(node)
    if core is None:
        return False
    name = _simple_name(core)
    if name in LOOSE_VALUE:
        return True
    if name in DICT_OUTER:
        return True
    if isinstance(core, ast.Subscript):
        outer = _simple_name(core.value)
        if outer in DICT_OUTER:
            return _dict_is_loose(core)
        if outer in LIST_OUTER:
            inner = _subscript_slice(core)
            return inner is not None and is_loose_structured_annotation(inner)
    return False


def _unwrap_optional(node: ast.expr) -> ast.expr | None:
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        left, right = node.left, node.right
        if _is_none_const(left):
            return _unwrap_optional(right) or right
        if _is_none_const(right):
            return _unwrap_optional(left) or left
        return None
    if isinstance(node, ast.Subscript):
        outer = _simple_name(node.value)
        if outer in {"Optional", "Union"}:
            sl = _subscript_slice(node)
            if sl is None:
                return None
            if isinstance(sl, ast.Tuple):
                non_none = [e for e in sl.elts if not _is_none_const(e)]
                if len(non_none) == 1:
                    return _unwrap_optional(non_none[0]) or non_none[0]
                return None
            return _unwrap_optional(sl) or sl
    return node


def _is_none_const(node: ast.expr) -> bool:
    return (isinstance(node, ast.Constant) and node.value is None) or (
        isinstance(node, ast.Name) and node.id == "None"
    )


def _simple_name(node: ast.expr | None) -> str | None:
    if node is None:
        return None
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript):
        return _simple_name(node.value)
    return None


def _subscript_slice(node: ast.Subscript) -> ast.expr | None:
    sl = node.slice
    if isinstance(sl, ast.Tuple):
        return sl
    return sl


def _ann_text(node: ast.expr) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return "<annotation>"


def _iter_params(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.arg]:
    args = node.args
    out: list[ast.arg] = []
    out.extend(args.posonlyargs)
    out.extend(args.args)
    if args.vararg is not None:
        out.append(args.vararg)
    out.extend(args.kwonlyargs)
    if args.kwarg is not None:
        out.append(args.kwarg)
    return out


def _on_public_api(info: CallableInfo) -> bool:
    if info.name.startswith("_"):
        return False
    return info.is_public


def _cross_module(own_module: str, caller_modules: set[str]) -> bool:
    return any(m != own_module for m in caller_modules)


def _key_vocab_for_name(node: ast.AST, name: str) -> int:
    keys: set[str] = set()
    for child in ast.walk(node):
        key = _string_subscript_key(child, name)
        if key is not None:
            keys.add(key)
            continue
        key = _string_get_key(child, name)
        if key is not None:
            keys.add(key)
    return len(keys)


def _key_vocab_in_returns(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    keys: set[str] = set()
    for child in ast.walk(node):
        if not isinstance(child, ast.Return) or child.value is None:
            continue
        keys.update(_dict_literal_keys(child.value))
    return len(keys)


def _dict_literal_keys(expr: ast.expr) -> set[str]:
    if isinstance(expr, ast.Dict):
        out: set[str] = set()
        for k in expr.keys:
            if isinstance(k, ast.Constant) and isinstance(k.value, str):
                out.add(k.value)
        return out
    if isinstance(expr, ast.Call) and _simple_name(expr.func) == "dict":
        out = set()
        for kw in expr.keywords:
            if kw.arg is not None:
                out.add(kw.arg)
        return out
    return set()


def _string_subscript_key(node: ast.AST, name: str) -> str | None:
    if not isinstance(node, ast.Subscript):
        return None
    if not (isinstance(node.value, ast.Name) and node.value.id == name):
        return None
    sl = node.slice
    if isinstance(sl, ast.Constant) and isinstance(sl.value, str):
        return sl.value
    return None


def _string_get_key(node: ast.AST, name: str) -> str | None:
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    if not (
        isinstance(func, ast.Attribute)
        and func.attr == "get"
        and isinstance(func.value, ast.Name)
        and func.value.id == name
    ):
        return None
    if not node.args:
        return None
    arg0 = node.args[0]
    if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
        return arg0.value
    return None


def _wire_coerce_exempt(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    param: str,
    index: SymbolIndex,
) -> bool:
    """Exempt when the bag param is only fed into a record constructor / from_dict."""
    uses = [
        n
        for n in ast.walk(node)
        if isinstance(n, ast.Name) and n.id == param and isinstance(n.ctx, ast.Load)
    ]
    if not uses:
        return False
    return all(_name_only_in_coerce_call(node, use, index) for use in uses)


def _name_only_in_coerce_call(
    fn: ast.FunctionDef | ast.AsyncFunctionDef,
    name_node: ast.Name,
    index: SymbolIndex,
) -> bool:
    for parent in ast.walk(fn):
        if not isinstance(parent, ast.Call):
            continue
        if not any(child is name_node for child in ast.walk(parent)):
            continue
        # Name must be a direct arg, not nested in a non-coerce expression
        if not _is_direct_call_arg(parent, name_node):
            return False
        return _call_looks_like_coerce(parent, index)
    return False


def _is_direct_call_arg(call: ast.Call, name_node: ast.Name) -> bool:
    if any(arg is name_node for arg in call.args):
        return True
    return any(kw.value is name_node for kw in call.keywords)


def _call_looks_like_coerce(call: ast.Call, index: SymbolIndex) -> bool:
    func = call.func
    if isinstance(func, ast.Attribute) and func.attr in COERCE_ATTRS:
        return True
    target = _simple_name(func)
    if target is None:
        return False
    # Constructor of a known record class in the index
    return any(ci.name == target and _class_is_record(ci.node) for ci in index.classes.values())


def _return_is_coerced_record(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    index: SymbolIndex,
) -> bool:
    """True when every returned value is a record constructor (annotation may still say dict)."""
    returns = [r for r in ast.walk(node) if isinstance(r, ast.Return) and r.value is not None]
    if not returns:
        return False
    return all(
        isinstance(r.value, ast.Call) and _call_looks_like_coerce(r.value, index) for r in returns
    )


def _class_is_record(node: ast.ClassDef) -> bool:
    for dec in node.decorator_list:
        name = _decorator_name(dec)
        if name in RECORD_DECORATORS:
            return True
    return any(_simple_name(base) in RECORD_BASE_SUFFIXES for base in node.bases)


def _decorator_name(dec: ast.expr) -> str | None:
    if isinstance(dec, ast.Call):
        return _simple_name(dec.func)
    return _simple_name(dec)
