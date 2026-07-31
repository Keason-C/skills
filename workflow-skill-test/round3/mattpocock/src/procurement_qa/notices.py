"""判断一个问题是不是碰到了被挡下的保密文档。

这是 ADR-0002 的次生问题:保密文档既然对模型不可见,系统怎么知道该告诉
采购员"这个问题涉及保密"?答案是**在进程内、不经过模型**地判断 ——
拿问题和被挡下文档的"标题 + 品类"做字符二元组重合度计算。

被挡下文档的信息只在本进程内参与一次布尔判断,永远不进入任何发给模型的字符串。
中文没有空格,所以用字符二元组而不是分词 —— 不引入分词器,不引入新的调参面。
"""

from __future__ import annotations

import re

from .model import Document, Handover

#: 保密话题词。命中其中之一 + 问题里点到了某个品类,就算碰到了那个品类的保密文档。
RESTRICTED_KEYWORDS: tuple[str, ...] = (
    "报价",
    "价格",
    "单价",
    "成本",
    "底价",
    "折扣",
    "让价",
    "毛利",
    "议价",
    "返点",
    "谈判策略",
)

#: 标题重合度达到这个数就算相关。2 个二元组 ≈ 3 个连续汉字,足够避免误报。
OVERLAP_THRESHOLD = 2

_PUNCTUATION = ",。?!、:;“”‘’()《》[]{}.,?!:;-—…\"'"
_NOISE = re.compile(r"[\s" + re.escape(_PUNCTUATION) + r"]")


def bigrams(text: str) -> set[str]:
    cleaned = _NOISE.sub("", text)
    return {cleaned[i : i + 2] for i in range(len(cleaned) - 1)}


def relevant_withheld(
    question: str,
    withheld: tuple[Document, ...],
    *,
    keywords: tuple[str, ...] = RESTRICTED_KEYWORDS,
) -> tuple[Document, ...]:
    """从被挡下的文档里挑出与问题相关的那些。"""
    question_grams = bigrams(question)
    mentions_restricted_topic = any(word in question for word in keywords)

    hits: list[Document] = []
    for doc in withheld:
        overlap = len(question_grams & bigrams(f"{doc.title}{doc.category}"))
        if overlap >= OVERLAP_THRESHOLD:
            hits.append(doc)
        elif mentions_restricted_topic and doc.category and doc.category in question:
            hits.append(doc)
    return tuple(hits)


def build_restricted_notice(hits: tuple[Document, ...], handover: Handover) -> str:
    """明说但不透露:承认存在,不泄露内容(业主确认的 (a) 方案)。

    注意这里只用到转人工目标的姓名和联系方式,**一个字的文档内容都不引用**。
    """
    if not hits:
        return ""
    contact = f"({handover.to_contact})" if handover.to_contact else ""
    return (
        "该问题涉及保密内容(供应商报价、成本、谈判策略),你的权限看不到。"
        f"已转给 {handover.to_name}{contact}。"
    )
