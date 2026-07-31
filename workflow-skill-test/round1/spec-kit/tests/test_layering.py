"""Architectural layering, enforced (task T064).

The constitution mandates one-way dependencies `models -> tools -> drivers -> guards ->
pipeline`, and specifically that **guards must not import drivers**. That rule is what keeps
the guards pure -- a guard able to call an LLM would put a business decision back inside the
probabilistic component, defeating Principle I.

A rule nobody checks is a comment, so this checks it by reading the AST rather than by
trusting reviewers.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import triagebot

PACKAGE_ROOT = Path(triagebot.__file__).parent
GUARD_MODULES = sorted((PACKAGE_ROOT / "guards").glob("*.py"))


def imported_modules(path: Path) -> set[str]:
    """Every module name this file imports, absolute and relative alike."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            # level>0 is a relative import; ".." from guards/ means the package root.
            prefix = "." * node.level
            found.add(f"{prefix}{node.module or ''}")
    return found


def test_guard_modules_exist() -> None:
    assert GUARD_MODULES, "no guard modules found - the layering test would pass vacuously"


@pytest.mark.parametrize("path", GUARD_MODULES, ids=lambda p: p.name)
def test_guards_do_not_import_drivers(path: Path) -> None:
    for name in imported_modules(path):
        assert "drivers" not in name, f"{path.name} imports {name}: guards must stay pure"


@pytest.mark.parametrize("path", GUARD_MODULES, ids=lambda p: p.name)
def test_guards_do_not_import_the_pipeline(path: Path) -> None:
    """Upwards imports would make the layering circular."""
    for name in imported_modules(path):
        assert "pipeline" not in name, f"{path.name} imports {name}"


@pytest.mark.parametrize("path", GUARD_MODULES, ids=lambda p: p.name)
def test_guards_perform_no_io(path: Path) -> None:
    """Purity, checked structurally: no filesystem, network, clock, or randomness."""
    forbidden = {"random", "requests", "httpx", "urllib", "socket", "time", "os"}
    for name in imported_modules(path):
        root = name.lstrip(".").split(".")[0]
        assert root not in forbidden, f"{path.name} imports {name}: guards must be pure"


def test_guards_do_not_read_the_clock() -> None:
    """`datetime.now`/`date.today` inside a guard would break SC-004 silently."""
    for path in GUARD_MODULES:
        source = path.read_text(encoding="utf-8")
        assert "date.today()" not in source, f"{path.name} reads the clock"
        assert "datetime.now(" not in source, f"{path.name} reads the clock"


def test_pipeline_is_the_only_module_importing_both_sides() -> None:
    both: list[str] = []
    for path in PACKAGE_ROOT.rglob("*.py"):
        names = imported_modules(path)
        has_drivers = any("drivers" in name for name in names)
        has_guards = any("guards" in name for name in names)
        if has_drivers and has_guards:
            both.append(path.name)
    assert both == ["pipeline.py"], f"expected only pipeline.py to join both halves, got {both}"


def test_models_module_depends_on_nothing_internal() -> None:
    """`models` is the base of the stack; an internal import here would invert the layering."""
    internal = {
        name
        for name in imported_modules(PACKAGE_ROOT / "models.py")
        if name.startswith(".") or name.startswith("triagebot")
    }
    assert internal == set(), f"models.py should be self-contained, imports {internal}"
