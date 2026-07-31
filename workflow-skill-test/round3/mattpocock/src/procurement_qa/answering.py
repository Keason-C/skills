"""问答核心。

深模块:接口是一个函数,内部藏着两段式选材、结构化输出解析、出处逐字核验、
弃答降级、保密提示与转人工构造。

它**不打印任何东西、不读 argv、不知道命令行存在**,也不写任何文件 ——
返回结果,不产生副作用。命令行只是它的第一个前端;企业微信以后是第二个。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from .access import visible_to
from .llm import LlmDriver
from .model import (
    AbstainReason,
    Answer,
    Asker,
    Citation,
    Document,
    Handover,
    Library,
)
from .notices import build_restricted_notice, relevant_withheld
from .people import Roster

MAX_DOCUMENTS = 4
_WHITESPACE = re.compile(r"\s+")

ABSTAIN_TEXT = "我不知道 —— 库里现有的文档回答不了这个问题,已转给人工。"

SELECTION_PROMPT = """你在帮采购部的同事从知识库里挑资料。

下面是知识库的目录,每份文档一条。请判断回答这个问题需要翻开哪几份文档的正文,
最多挑 {limit} 份;宁缺毋滥,不相关的不要挑。

只输出一个 JSON 数组,里面是文档编号字符串,不要任何解释。例如:["品类/某文档.docx"]
如果一份都不相关,输出 []。

问题:{question}

知识目录:
{catalog}"""

ANSWER_PROMPT = """你是采购部的知识问答助手。只根据下面给出的文档回答问题,不许用文档以外的知识。

规则:
1. 每一条论断都必须给出**出处**:文档编号 + 从该文档里**逐字抄下来**的原文片段。
   片段必须一字不差地出现在原文里,不许改写、不许概括、不许拼接。
2. 文档里没有的,就把 answered 设为 false 并在 reason 里说明缺什么。不许猜,不许编。
3. 若多份文档说法**不一致**,把两个说法并排列出并标注各自的生效日期,**不要替用户裁决**。
4. 用中文回答。

只输出一个 JSON 对象,不要任何解释或代码块标记:
{{"answered": true/false, "answer": "回答正文", "citations": [{{"document_id": "...", "quote": "原文片段"}}], "reason": "答不了时说明原因"}}

问题:{question}

文档(按生效日期从新到旧排列):
{documents}"""


@dataclass(frozen=True)
class _Verdict:
    answered: bool
    answer: str
    citations: tuple[Citation, ...]
    reason: str


def answer_question(
    *,
    question: str,
    asker: Asker,
    library: Library,
    driver: LlmDriver,
    roster: Roster,
    max_documents: int = MAX_DOCUMENTS,
) -> Answer:
    """回答一个问题。一切异常都收敛到弃答(ADR-0003)。"""
    view = visible_to(library, asker)

    # 保密相关性判断在进程内完成,被挡下的文档绝不进 prompt(ADR-0002)。
    hits = relevant_withheld(question, view.withheld)
    category = _target_category(question, hits, library, roster)
    handover = _handover_for(category, roster)
    notice = build_restricted_notice(hits, handover)
    withheld_titles = tuple(doc.title for doc in hits)

    def abstain(reason: AbstainReason) -> Answer:
        return Answer(
            text=ABSTAIN_TEXT,
            abstained=True,
            abstain_reason=reason,
            restricted_notice=notice,
            withheld_titles=withheld_titles,
            handover=handover,
        )

    if not view.visible:
        return abstain(AbstainReason.NO_VISIBLE_DOCUMENTS)

    try:
        selected = _select(question, view.visible, driver, max_documents)
    except Exception:
        return abstain(AbstainReason.DRIVER_ERROR)
    if not selected:
        return abstain(AbstainReason.NO_DOCUMENTS_SELECTED)

    ordered = _order_by_recency(selected)
    try:
        raw = driver.complete(build_answer_prompt(question, ordered))
    except Exception:
        return abstain(AbstainReason.DRIVER_ERROR)

    verdict = _parse_verdict(raw)
    if verdict is None:
        return abstain(AbstainReason.INVALID_JSON)
    if not verdict.answered:
        return abstain(AbstainReason.MODEL_ABSTAINED)
    if not verdict.citations:
        return abstain(AbstainReason.NO_CITATIONS)

    problem = _verify_citations(verdict.citations, ordered)
    if problem is not None:
        return abstain(problem)

    return Answer(
        text=verdict.answer,
        citations=verdict.citations,
        abstained=False,
        restricted_notice=notice,
        withheld_titles=withheld_titles,
        handover=handover if notice else None,
    )


# --- 两段式选材(ADR-0001) ----------------------------------------------


def build_catalog(documents: tuple[Document, ...]) -> str:
    lines = []
    for doc in documents:
        date = doc.effective_date.isoformat() if doc.effective_date else "未标注"
        summary = doc.summary or "(无摘要)"
        lines.append(
            f"- 编号:{doc.document_id} | 标题:{doc.title} | 品类:{doc.category} "
            f"| 生效日期:{date} | 摘要:{summary}"
        )
    return "\n".join(lines)


def build_selection_prompt(question: str, documents: tuple[Document, ...], limit: int) -> str:
    return SELECTION_PROMPT.format(
        limit=limit, question=question, catalog=build_catalog(documents)
    )


def build_answer_prompt(question: str, documents: tuple[Document, ...]) -> str:
    blocks = []
    for doc in documents:
        date = doc.effective_date.isoformat() if doc.effective_date else "未标注"
        blocks.append(
            f"=== 编号:{doc.document_id} | 标题:{doc.title} | 品类:{doc.category} "
            f"| 生效日期:{date} ===\n{doc.text}"
        )
    return ANSWER_PROMPT.format(question=question, documents="\n\n".join(blocks))


def _select(
    question: str, visible: tuple[Document, ...], driver: LlmDriver, limit: int
) -> tuple[Document, ...]:
    raw = driver.complete(build_selection_prompt(question, visible, limit))
    known = {doc.document_id: doc for doc in visible}

    ids = _parse_id_list(raw)
    if ids is None:
        # 模型没给合法 JSON 就退一步:看看输出里有没有出现已知的文档编号。
        ids = [doc_id for doc_id in known if doc_id in raw]

    chosen: list[Document] = []
    for doc_id in ids:
        doc = known.get(doc_id)
        if doc is not None and doc not in chosen:
            chosen.append(doc)
        if len(chosen) >= limit:
            break
    return tuple(chosen)


def _order_by_recency(documents: tuple[Document, ...]) -> tuple[Document, ...]:
    """有生效日期的在前(新的更前),无日期的垫底,同类按编号稳定排序。"""
    return tuple(
        sorted(
            documents,
            key=lambda d: (
                0 if d.effective_date else 1,
                -d.effective_date.toordinal() if d.effective_date else 0,
                d.document_id,
            ),
        )
    )


# --- 出处核验(ADR-0003) ------------------------------------------------


def _verify_citations(
    citations: tuple[Citation, ...], fed: tuple[Document, ...]
) -> AbstainReason | None:
    by_id = {doc.document_id: doc for doc in fed}
    for citation in citations:
        doc = by_id.get(citation.document_id)
        if doc is None:
            return AbstainReason.UNKNOWN_DOCUMENT
        if not _contains_verbatim(doc.text, citation.quote):
            return AbstainReason.QUOTE_NOT_FOUND
    return None


def _contains_verbatim(text: str, quote: str) -> bool:
    """规范化空白后做子串匹配 —— 换行和空格的差异不算对不上,改字算。"""
    if not quote.strip():
        return False
    return _squash(quote) in _squash(text)


def _squash(text: str) -> str:
    return _WHITESPACE.sub("", text)


# --- 解析 ----------------------------------------------------------------


def _parse_id_list(raw: str) -> list[str] | None:
    start, end = raw.find("["), raw.rfind("]")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(data, list):
        return None
    return [item for item in data if isinstance(item, str)]


def _parse_verdict(raw: str) -> _Verdict | None:
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or "answered" not in data:
        return None

    citations: list[Citation] = []
    for item in data.get("citations") or []:
        if isinstance(item, dict) and "document_id" in item and "quote" in item:
            citations.append(
                Citation(document_id=str(item["document_id"]), quote=str(item["quote"]))
            )

    return _Verdict(
        answered=bool(data.get("answered")),
        answer=str(data.get("answer") or ""),
        citations=tuple(citations),
        reason=str(data.get("reason") or ""),
    )


# --- 转人工 --------------------------------------------------------------


def _target_category(
    question: str, hits: tuple[Document, ...], library: Library, roster: Roster
) -> str:
    """这个问题该算在哪个品类头上 —— 只用来决定转给谁,不参与任何权限判断。

    已知很粗:靠"品类名是不是问题的子串"来认。目录名当品类的代价在这里显形
    (问「**流程**上有什么要求」会被算成「流程」品类)。所以在多个候选之间
    优先挑名单里真有人管的那个 —— 转错人比转给兜底更糟。
    拿到真语料后应改成用名单里的品类白名单,见 `.scratch/.../code-review.md` Spec #7。
    """
    if hits:
        return hits[0].category
    mentioned = [
        category
        for category in dict.fromkeys(doc.category for doc in library.documents)
        if category and category in question
    ]
    managed = [c for c in mentioned if roster.manager_of(c) is not None]
    if managed:
        return managed[0]
    return mentioned[0] if mentioned else ""


def _handover_for(category: str, roster: Roster) -> Handover:
    manager = roster.manager_of(category) if category else None
    if manager is not None:
        return Handover(
            to_name=manager.name,
            to_contact=manager.contact,
            category=category,
            is_fallback=False,
        )
    return Handover(
        to_name=roster.fallback.name,
        to_contact=roster.fallback.contact,
        category=category,
        is_fallback=True,
    )
