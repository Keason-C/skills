"""同一主题的多个版本 —— 需求方亲自定的规则(FR-005a / FR-005b)。

需求方原话:
  "文件里写了生效日期或版本号的,按新的答,同时注明『另有旧版』;
   俩文件比不出新旧的(都没写日期),就两份并列摆出提示『资料不一致,请自行核实』,
   机器人别硬挑。我们的文件大多没版本号,所以并列摆出会是常态,没关系。"

**能力边界**:我们检测的是"同一主题的多个版本",不是"任意语义矛盾"。
后者无法用确定性代码可靠判定,让 LLM 去判会把幻觉引入一个本该确定的环节。
这一点在 README 里对用户明说(D-08)。
"""

from __future__ import annotations

from .ingest.loader import IndexData
from .models import ConflictGroup, DateConfidence, Document
from .retrieval import ScoredPassage

JACCARD_THRESHOLD = 0.6


def _jaccard(a: tuple[str, ...], b: tuple[str, ...]) -> float:
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _sort_key(doc: Document) -> tuple:
    return (
        doc.effective_date or __import__("datetime").date.min,
        doc.version or "",
        doc.doc_id,
    )


def _comparable(doc: Document) -> bool:
    """能不能参与新旧比较。

    只有 body 级置信度的日期、或显式版本号才算数。文件名推断出来的年份
    只有在**双方都是文件名推断**时才参与排序(D-07),这里保守处理:
    单独的 filename 置信度不足以裁决。
    """
    return doc.date_confidence is DateConfidence.BODY or doc.version is not None


def detect_groups(scored: list[ScoredPassage], index: IndexData) -> list[ConflictGroup]:
    """把命中的文档按"同主题"聚簇,再按需求方的规则裁决。"""
    docs_by_id = index.docs_by_id
    hit_ids: list[str] = []
    for sp in scored:
        if sp.passage.doc_id not in hit_ids:
            hit_ids.append(sp.passage.doc_id)

    hits = [docs_by_id[d] for d in hit_ids if d in docs_by_id]
    if len(hits) < 2:
        return []

    used: set[str] = set()
    groups: list[ConflictGroup] = []

    for i, doc in enumerate(hits):
        if doc.doc_id in used:
            continue
        cluster = [doc]
        for other in hits[i + 1 :]:
            if other.doc_id in used:
                continue
            if _jaccard(doc.title_tokens, other.title_tokens) >= JACCARD_THRESHOLD:
                cluster.append(other)
        if len(cluster) < 2:
            continue
        for d in cluster:
            used.add(d.doc_id)
        groups.append(_resolve(cluster))

    return groups


def _resolve(cluster: list[Document]) -> ConflictGroup:
    doc_ids = tuple(sorted(d.doc_id for d in cluster))

    if all(_comparable(d) for d in cluster):
        # FR-005a:按新的答,注明另有旧版
        ordered = sorted(cluster, key=_sort_key, reverse=True)
        primary = ordered[0]
        return ConflictGroup(
            doc_ids=doc_ids,
            resolution="superseded",
            primary_doc_id=primary.doc_id,
            superseded_doc_ids=tuple(d.doc_id for d in ordered[1:]),
        )

    # FR-005b:比不出新旧 → 并列摆出,机器人不硬挑
    return ConflictGroup(doc_ids=doc_ids, resolution="unresolved")


def notices_for(groups: list[ConflictGroup], index: IndexData) -> tuple[str, ...]:
    """把裁决结果翻译成给采购员看的人话提示。"""
    docs = index.docs_by_id
    out: list[str] = []
    for g in groups:
        if g.resolution == "superseded":
            olds = []
            for did in g.superseded_doc_ids:
                d = docs.get(did)
                if d is None:
                    continue
                when = f"(生效日期 {d.effective_date})" if d.effective_date else ""
                olds.append(f"《{d.filename}》{when}")
            if olds:
                out.append(f"另有旧版:{'、'.join(olds)},本次未采用。")
        else:
            names = [f"《{docs[d].filename}》" for d in g.doc_ids if d in docs]
            out.append(
                f"资料不一致,请自行核实:{'、'.join(names)} 均未标注生效日期或版本号,"
                "系统不做裁决。"
            )
    return tuple(out)


def demoted_doc_ids(groups: list[ConflictGroup]) -> set[str]:
    """被判定为旧版、不应作为答案依据的文档。"""
    out: set[str] = set()
    for g in groups:
        if g.resolution == "superseded":
            out |= set(g.superseded_doc_ids)
    return out
