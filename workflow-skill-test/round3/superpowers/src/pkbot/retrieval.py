"""确定性检索:关键词打分 + 上下文预算装载。

刻意不含任何模型调用——决定"读哪份"的逻辑必须能被完整单测,
否则"答得准"这个要求就没有可验证的底座。这也是不上向量库的原因之一。
"""

from __future__ import annotations

import math
import re
from collections import Counter

from .models import ContextPack, Document, LoadedDoc, Section

DEFAULT_BUDGET = 100_000

_LATIN = re.compile(r"[a-zA-Z0-9_./x-]+")
_CJK_CHAR = re.compile(r"[一-鿿]")


def tokenize(text: str) -> list[str]:
    """中文取相邻二字组合,英文/编号取整词。纯字符串处理,结果稳定可测。"""
    tokens = [m.group(0).lower() for m in _LATIN.finditer(text)]

    runs: list[str] = []
    current: list[str] = []
    for ch in text:
        if _CJK_CHAR.match(ch):
            current.append(ch)
        elif current:
            runs.append("".join(current))
            current = []
    if current:
        runs.append("".join(current))

    for run in runs:
        if len(run) == 1:
            tokens.append(run)
        else:
            tokens.extend(run[i : i + 2] for i in range(len(run) - 1))
    return tokens


def _term_freq(text: str) -> Counter[str]:
    return Counter(tokenize(text))


def score_document(
    query_terms: set[str], tf: Counter[str], corpus_size: int, df: Counter[str]
) -> float:
    """BM25 精神的简化版:词频取对数饱和,乘以逆文档频率压制通用词。"""
    score = 0.0
    for term in query_terms:
        freq = tf.get(term, 0)
        if freq == 0:
            continue
        idf = math.log(1 + corpus_size / (1 + df.get(term, 0)))
        score += (1 + math.log(freq)) * idf
    return score


def rank(question: str, docs: list[Document]) -> list[tuple[Document, float]]:
    query_terms = set(tokenize(question))
    if not query_terms or not docs:
        return []
    tfs = {doc.doc_id: _term_freq(doc.full_text) for doc in docs}
    df: Counter[str] = Counter()
    for tf in tfs.values():
        df.update(set(tf))
    scored = [
        (doc, score_document(query_terms, tfs[doc.doc_id], len(docs), df)) for doc in docs
    ]
    scored = [(doc, s) for doc, s in scored if s > 0]
    scored.sort(key=lambda pair: (-pair[1], pair[0].doc_id))
    return scored


def matched_term_count(question: str, doc: Document) -> int:
    """文档命中了问题里多少个**不同**的词。

    用来区分"真的相关"和"只是有个通用词沾边"——单个二元组命中(比如
    问包装材料、文档里恰好有"原材料")属于噪音,不足以断言相关。
    """
    query_terms = set(tokenize(question))
    if not query_terms:
        return 0
    doc_terms = set(tokenize(doc.full_text))
    return len(query_terms & doc_terms)


def _rank_section_indices(
    query_terms: set[str], sections: tuple[Section, ...]
) -> list[int]:
    scored: list[tuple[float, int]] = []
    for idx, sec in enumerate(sections):
        tf = _term_freq(sec.text)
        hits = sum(tf.get(term, 0) for term in query_terms)
        if hits:
            scored.append((float(hits), idx))
    scored.sort(key=lambda pair: (-pair[0], pair[1]))
    return [idx for _, idx in scored]


def build_context(
    question: str, docs: list[Document], budget: int = DEFAULT_BUDGET
) -> ContextPack:
    """按相关度装载:装得下整篇就整篇;装不下就只装命中的小节;再装不下就如实跳过。

    "跳过"必须被记录并最终告诉用户——这是"大文件读不动宁可说读不动"的落点。
    """
    query_terms = set(tokenize(question))
    ranked = rank(question, docs)
    remaining = budget
    loaded: list[LoadedDoc] = []
    skipped: list[str] = []

    for doc, _score in ranked:
        if doc.token_estimate <= remaining:
            loaded.append(LoadedDoc(doc.doc_id, doc.title, doc.sections, partial=False))
            remaining -= doc.token_estimate
            continue

        picked_indices: list[int] = []
        for idx in _rank_section_indices(query_terms, doc.sections):
            if doc.sections[idx].token_estimate <= remaining:
                picked_indices.append(idx)
                remaining -= doc.sections[idx].token_estimate
        if picked_indices:
            ordered = tuple(doc.sections[i] for i in sorted(picked_indices))
            loaded.append(LoadedDoc(doc.doc_id, doc.title, ordered, partial=True))
        else:
            skipped.append(doc.title)

    return ContextPack(tuple(loaded), tuple(skipped))
