"""Unit tests for DOU (dict-overuse) L1 detection."""

from __future__ import annotations

import ast
from pathlib import Path

from py_code_metrics.metrics.dou import analyze_dou, is_loose_structured_annotation
from py_code_metrics.resolve import CallableInfo, SymbolIndex


def _ann(src: str) -> ast.expr:
    mod = ast.parse(f"x: {src}")
    assert isinstance(mod.body[0], ast.AnnAssign)
    assert mod.body[0].annotation is not None
    return mod.body[0].annotation


def test_loose_annotation_grammar():
    assert is_loose_structured_annotation(_ann("dict[str, Any]"))
    assert is_loose_structured_annotation(_ann("dict[str, object]"))
    assert is_loose_structured_annotation(_ann("dict"))
    assert is_loose_structured_annotation(_ann("Mapping[str, Any]"))
    assert is_loose_structured_annotation(_ann("list[dict[str, Any]]"))
    assert is_loose_structured_annotation(_ann("dict[str, Any] | None"))
    assert is_loose_structured_annotation(_ann("Optional[dict[str, Any]]"))

    assert not is_loose_structured_annotation(_ann("dict[str, int]"))
    assert not is_loose_structured_annotation(_ann("dict[str, CallableMetrics]"))
    assert not is_loose_structured_annotation(_ann("list[int]"))
    assert not is_loose_structured_annotation(_ann("int"))


def _callable(src: str, *, name: str = "fn") -> tuple[CallableInfo, SymbolIndex]:
    tree = ast.parse(src)
    fn = next(
        n
        for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name
    )
    info = CallableInfo(
        qname=f"mod.{name}",
        name=name,
        module="mod",
        kind="function",
        node=fn,
        is_public=not name.startswith("_"),
        lineno=fn.lineno,
    )
    index = SymbolIndex(root=Path("."))
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            from py_code_metrics.resolve import ClassInfo

            index.classes[f"mod.{node.name}"] = ClassInfo(
                qname=f"mod.{node.name}",
                name=node.name,
                module="mod",
                node=node,
            )
    index.callables[info.qname] = info
    return info, index


def test_analyze_dou_flags_param_and_return():
    src = """
def fn(cfg: dict[str, Any]) -> dict[str, Any]:
    return {"a": cfg["x"], "b": 1}
"""
    info, index = _callable(src)
    result = analyze_dou(info, index=index, fan_in_ext=3, caller_modules={"other"})
    assert result.n_sites == 2
    sites = {s.site for s in result.sites}
    assert sites == {"param", "return"}
    param = next(s for s in result.sites if s.site == "param")
    assert param.impact.fan_out_sites == 3
    assert param.impact.cross_module is True
    assert param.impact.on_public_api is True
    assert param.impact.key_vocab_size >= 1


def test_analyze_dou_skips_homogeneous_index():
    src = """
def fn(counts: dict[str, int]) -> dict[str, CallableMetrics]:
    return counts  # type: ignore
"""
    info, index = _callable(src)
    result = analyze_dou(info, index=index, fan_in_ext=0, caller_modules=set())
    assert result.n_sites == 0


def test_wire_coerce_exempts_param():
    src = """
from dataclasses import dataclass

@dataclass
class Cfg:
    x: int

def load(raw: dict[str, Any]) -> Cfg:
    return Cfg(raw)
"""
    # Cfg(raw) is a stretch — typically Cfg(**raw) or Cfg.from_dict(raw)
    info, index = _callable(src, name="load")
    # Direct constructor arg
    result = analyze_dou(info, index=index, fan_in_ext=1, caller_modules=set())
    assert result.n_sites == 0


def test_wire_coerce_from_dict():
    src = """
from dataclasses import dataclass

@dataclass
class Cfg:
    @classmethod
    def from_dict(cls, data):
        return cls()

def load(raw: dict[str, Any]) -> Cfg:
    return Cfg.from_dict(raw)
"""
    info, index = _callable(src, name="load")
    result = analyze_dou(info, index=index, fan_in_ext=1, caller_modules=set())
    assert result.n_sites == 0
