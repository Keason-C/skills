"""问答内核。

模型只负责组织语言并报出引用;是否可信由系统侧的**引用校验闸门**决定。
这不是在提示词里请模型别瞎编——是它编了也过不去这道闸门。
"""

from __future__ import annotations

import json

from .drivers import LLMDriver
from .models import Answer, Citation, ContextPack

SYSTEM_PROMPT = """你是某公司采购部的知识助手,只能依据下面提供的资料回答问题。

铁律:
1. 只能使用【资料】中出现的内容。资料里没有的,一律回答 no_answer,绝不依靠常识或推测补充。
2. 每条回答必须给出引用,引用的 doc_id 必须逐字来自【资料】中标注的 doc_id。
3. 不确定、资料只是沾边、需要跨文档推断才能得出结论时,一律 no_answer。
4. 用简体中文回答,面向没有技术背景的采购员,直接给结论。

只输出一个 JSON 对象,不要有任何其他文字:
{"status": "answered" 或 "no_answer",
 "answer": "回答正文(no_answer 时为空字符串)",
 "citations": [{"doc_id": "资料里的 doc_id", "locator": "资料里的出处标记"}]}
"""

FAILURE_TEXT = "这个问题我答不上来,已经记录下来,会有人跟进。"


def render_context(pack: ContextPack) -> str:
    blocks: list[str] = []
    for doc in pack.docs:
        parts = [f'<资料 doc_id="{doc.doc_id}" 标题="{doc.title}">']
        if doc.partial:
            parts.append("(注意:本文档过大,以下仅为与问题相关的部分章节)")
        for sec in doc.sections:
            parts.append(f"[出处:{sec.locator}]\n{sec.text}")
        parts.append("</资料>")
        blocks.append("\n".join(parts))
    return "\n\n".join(blocks)


def parse_response(raw: str) -> dict | None:
    text = raw.strip()
    if text.startswith("```"):
        lines = [ln for ln in text.splitlines() if not ln.strip().startswith("```")]
        text = "\n".join(lines).strip()
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def disclosures(pack: ContextPack) -> list[str]:
    """把"没读全"如实说出来。需求方原话:读不动宁可说读不动。

    与 _failed 里的内部诊断分开:这部分对用户永远有用,诊断不一定。
    """
    notes: list[str] = []
    for doc in pack.docs:
        if doc.partial:
            notes.append(f"提示:《{doc.title}》太大,我只读了与问题相关的部分章节。")
    for title in pack.skipped_oversized:
        notes.append(f"提示:《{title}》太大,这次没能读进来。")
    return notes


def _failed(reason: str, pack: ContextPack) -> Answer:
    return Answer("no_answer", FAILURE_TEXT, (), tuple([reason, *disclosures(pack)]))


def answer_question(driver: LLMDriver, question: str, pack: ContextPack) -> Answer:
    if not pack.docs:
        return Answer(
            "no_answer",
            FAILURE_TEXT,
            (),
            ("库里没有找到与这个问题相关的资料。", *disclosures(pack)),
        )

    user = f"【资料】\n{render_context(pack)}\n\n【问题】\n{question}"
    raw = driver.complete(SYSTEM_PROMPT, user)

    parsed = parse_response(raw)
    if parsed is None:
        return _failed("模型返回的格式不合法,为避免误导已作废。", pack)
    if parsed.get("status") != "answered":
        return _failed("模型判断资料不足以回答。", pack)

    text = (parsed.get("answer") or "").strip()
    raw_citations = parsed.get("citations") or []
    if not text or not isinstance(raw_citations, list) or not raw_citations:
        return _failed("答案缺少正文或出处,已作废。", pack)

    citations: list[Citation] = []
    for item in raw_citations:
        if not isinstance(item, dict):
            return _failed("引用格式不合法,已作废。", pack)
        doc_id = str(item.get("doc_id", ""))
        if doc_id not in pack.doc_ids:
            # 引用校验闸门:引用了本次没装载的文档,视为编造,整条作废。
            # 刻意不回显模型报出的 doc_id——它可能正是一份该用户无权看到的
            # 保密文档路径,回显等于隔着闸门把文件名漏出去。
            return _failed("答案引用了本次未读取的资料,疑似编造,已作废。", pack)
        locator = str(item.get("locator", "")).strip() or "未标注"
        citations.append(Citation(doc_id, locator))

    return Answer("answered", text, tuple(citations), tuple(disclosures(pack)))
