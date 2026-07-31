"""复用 scripts/build_demo_corpus.py 里的最小 PDF 生成器,避免重复实现。

用 importlib 按路径加载,免得为一个脚本去搞包结构。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "build_demo_corpus.py"

_spec = importlib.util.spec_from_file_location("_build_demo_corpus", _SCRIPT)
assert _spec and _spec.loader
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

make_pdf = _module.make_pdf
