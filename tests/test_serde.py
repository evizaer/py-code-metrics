"""Tests for annotation-driven dataclass ↔ dict mapping."""

from __future__ import annotations

from dataclasses import dataclass, field

from py_code_metrics.model import (
    ClassMetrics,
    HotspotEntry,
    ModuleReport,
    MutationSurvivor,
    UncoveredStateField,
)
from py_code_metrics.serde import MappingMixin, from_mapping, to_mapping


@dataclass
class _Sample(MappingMixin):
    name: str
    count: int = 0
    score: float | None = field(default=None, metadata={"omit_none": True})
    tags: list[str] = field(default_factory=list)


def test_roundtrip_primitives_and_omit_none():
    obj = _Sample(name="a", count=2, score=None, tags=["x"])
    assert obj.to_dict() == {"name": "a", "count": 2, "tags": ["x"]}
    back = _Sample.from_dict({"name": "a", "count": "2", "tags": [1]})
    assert back == _Sample(name="a", count=2, tags=["1"])


def test_key_rename_and_aliases():
    u = UncoveredStateField.from_dict({"class": "C", "field": "f"})
    assert u.class_ == "C"
    assert u.to_dict() == {"class": "C", "field": "f"}

    s = MutationSurvivor.from_dict({"path": "a.py", "line": "3"})
    assert s.file == "a.py"
    assert s.line == 3


def test_nest_metrics_and_imports():
    cls = ClassMetrics.from_dict(
        {
            "name": "A",
            "qualified_name": "m.A",
            "lineno": 1,
            "metrics": {"lcom4": 2, "wmc": 3},
            "methods": [],
        }
    )
    assert cls.lcom4 == 2
    assert cls.to_dict()["metrics"]["lcom4"] == 2

    # Flat back-compat for nested metric fields
    flat = ClassMetrics.from_dict(
        {"name": "A", "qualified_name": "m.A", "lineno": 1, "lcom4": 9}
    )
    assert flat.lcom4 == 9

    mod = ModuleReport.from_dict(
        {"path": "a.py", "name": "a", "imports": ["b"], "scc_id": 1}
    )
    assert mod.imports == ["b"]
    assert mod.scc_id == 1
    assert mod.to_dict()["imports"] == {"imports": ["b"], "scc_id": 1}


def test_hotspot_omits_null_path():
    h = HotspotEntry(qualified_name="a.f")
    assert "path" not in h.to_dict()
    h2 = HotspotEntry.from_dict({"qualified_name": "a.f", "path": "a.py"})
    assert h2.path == "a.py"


def test_from_mapping_empty_uses_defaults():
    obj = from_mapping(_Sample, {})
    assert obj.name == ""
    assert obj.count == 0
    assert to_mapping(obj)["tags"] == []
