"""把检索结果组装成给模型的请求。

注意调用位置:**这一步必须在 authz 过滤之后**(contracts/core-api.md CA-5)。
到了这里,受限内容已经不在 ``scored`` 里了。
"""

from __future__ import annotations

from .ingest.loader import IndexData
from .llm.base import LLMRequest, PassageView
from .retrieval import ScoredPassage

DEFAULT_TOP_K = 12


def source_label(index: IndexData, sp: ScoredPassage) -> str:
    doc = index.docs_by_id.get(sp.passage.doc_id)
    name = doc.filename if doc else sp.passage.doc_id
    return f"{name} — {sp.passage.locator}"


def build_request(
    question: str,
    scored: list[ScoredPassage],
    index: IndexData,
    top_k: int = DEFAULT_TOP_K,
) -> tuple[LLMRequest, bool]:
    """返回 (请求, 是否发生了截断)。

    截断必须被如实声明(FR-006)——不能让用户以为机器人通盘查阅过全部资料。
    """
    selected = scored[:top_k]
    partial = len(scored) > top_k
    views = tuple(
        PassageView(
            passage_id=sp.passage.passage_id,
            source_label=source_label(index, sp),
            text=sp.passage.text,
        )
        for sp in selected
    )
    return LLMRequest(question=question, passages=views), partial
