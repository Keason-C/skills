"""权限过滤(宪法原则 II / FR-009 ~ FR-012 / research.md D-06)。

**这个模块的位置就是它的意义**:它在检索与组 prompt **之前**运行。
受限内容不是"被叮嘱不要说出来",而是**根本没被交给模型**。
提示词注入可以绕过"请不要透露",绕不过"数据没被读进来"。

一个需要说清楚的边界:为了区分"公司没这份资料"和"你没权限看",系统需要知道
问题是否命中了受限材料。做法是对受限片段**单独打分,只保留分数与品类标签,
文本立即丢弃**。打分不是生成,不违反原则 II;并且有测试
(``test_restricted_text_never_leaves_authz``)断言受限正文不出现在
prompt / 审计 / 转人工记录 / CLI 输出的任何位置。
"""

from __future__ import annotations

from dataclasses import dataclass

from .ingest.loader import IndexData
from .models import ALL_CATEGORIES, Document, Passage, Requester, Sensitivity
from .retrieval import score

# 受限命中判定阈值:低于这个分数认为只是偶然词元重合,不算"问到了保密内容"
RESTRICTED_HIT_MIN_SCORE = 1.0


def can_access(requester: Requester, document: Document) -> bool:
    if document.sensitivity is Sensitivity.INTERNAL:
        return True
    if ALL_CATEGORIES in requester.categories:  # 采购负责人
        return True
    if document.category is None:
        # 保密根目录、未归品类 → 最保守:只有采购负责人
        return False
    return document.category in requester.categories


@dataclass(frozen=True)
class Partition:
    visible: list[Passage]
    restricted: list[Passage]  # 仅供打分探测,文本绝不外流


def partition(index: IndexData, requester: Requester) -> Partition:
    docs = index.docs_by_id
    visible: list[Passage] = []
    restricted: list[Passage] = []
    for p in index.passages:
        doc = docs.get(p.doc_id)
        if doc is None:
            continue
        (visible if can_access(requester, doc) else restricted).append(p)
    return Partition(visible=visible, restricted=restricted)


@dataclass(frozen=True)
class RestrictedProbe:
    hit: bool
    top_score: float
    categories: frozenset[str]
    # 命中的材料里有"未归品类"的保密文件吗?有的话只有采购负责人能处理,
    # 转给任何一位品类经理都是把人往墙上撞。
    uncategorised: bool = False


def restricted_hit_probe(
    question: str, part: Partition, index: IndexData
) -> RestrictedProbe:
    """问题是否命中了当前用户看不到的材料。

    **只返回布尔、分数和品类标签。受限文本在函数返回时就已经不可达了。**
    """
    if not part.restricted:
        return RestrictedProbe(hit=False, top_score=0.0, categories=frozenset())

    scored = score(question, part.restricted, index.idf)
    if not scored:
        return RestrictedProbe(hit=False, top_score=0.0, categories=frozenset())

    top = scored[0].score
    docs = index.docs_by_id
    strong = [
        docs[sp.passage.doc_id]
        for sp in scored
        if sp.score >= RESTRICTED_HIT_MIN_SCORE and sp.passage.doc_id in docs
    ]
    top_doc = docs.get(scored[0].passage.doc_id)
    return RestrictedProbe(
        hit=top >= RESTRICTED_HIT_MIN_SCORE,
        top_score=top,
        categories=frozenset(d.category for d in strong if d.category),
        uncategorised=bool(top_doc is not None and top_doc.category is None),
    )
