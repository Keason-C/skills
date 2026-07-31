"""确定性检索 —— 不用向量库(宪法原则 V / research.md D-01)。

分词策略:
* CJK 连续段 → 字符 **bigram**(三字词 → 两个二字片段)。不需要词典,
  对专有名词比分词器更稳。单字成段时保留该单字。
* ASCII → ``[a-z0-9]+`` 小写词。

打分:Σ(命中词元的 IDF) × 位置权重,标题命中 ×2.0,再按长度做轻度归一。
全程无随机性:同一输入永远同一输出(有测试断言这一点)。
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from .models import Passage

_CJK = r"一-鿿㐀-䶿"
_CJK_RUN = re.compile(f"[{_CJK}]+")
_ASCII_WORD = re.compile(r"[A-Za-z0-9]+")

HEADING_WEIGHT = 2.0


def tokenize(text: str) -> list[str]:
    """把文本切成可比较的词元。确定性、无外部词典。"""
    tokens: list[str] = []
    for run in _CJK_RUN.findall(text):
        if len(run) == 1:
            tokens.append(run)
        else:
            tokens.extend(run[i : i + 2] for i in range(len(run) - 1))
    tokens.extend(w.lower() for w in _ASCII_WORD.findall(text))
    return tokens


def build_idf(passages: list[Passage]) -> dict[str, float]:
    """从语料现算 IDF。几十份文档,毫秒级,不需要预训练资源。"""
    n = len(passages) or 1
    df: Counter[str] = Counter()
    for p in passages:
        df.update(set(tokenize(p.text)) | set(tokenize(" ".join(p.heading_path))))
    return {tok: math.log((n + 1) / (c + 1)) + 1.0 for tok, c in df.items()}


@dataclass(frozen=True)
class ScoredPassage:
    passage: Passage
    score: float
    matched: tuple[str, ...]  # 命中了哪些词元 —— 让结果可解释(宪法原则 V)


def score(
    question: str,
    passages: list[Passage],
    idf: dict[str, float],
    *,
    default_idf: float = 1.0,
) -> list[ScoredPassage]:
    """对每个片段打分,降序返回;分数为 0 的片段会被剔除。

    平分时按 ``passage_id`` 字典序升序,保证结果**完全确定**。
    """
    q_tokens = set(tokenize(question))
    if not q_tokens:
        return []

    scored: list[ScoredPassage] = []
    for p in passages:
        body = set(tokenize(p.text))
        head = set(tokenize(" ".join(p.heading_path)))
        matched = sorted(q_tokens & (body | head))
        if not matched:
            continue
        s = 0.0
        for tok in matched:
            w = idf.get(tok, default_idf)
            s += w * (HEADING_WEIGHT if tok in head else 1.0)
        # 轻度长度归一:避免长片段仅因为字多就赢
        s /= 1.0 + math.log(1.0 + len(p.text) / 500.0)
        scored.append(ScoredPassage(passage=p, score=round(s, 6), matched=tuple(matched)))

    scored.sort(key=lambda sp: (-sp.score, sp.passage.passage_id))
    return scored


# ---------------------------------------------------------------------------
# 未知词guard —— "宁可漏答不可错答"的落地
# ---------------------------------------------------------------------------

# 纯语言层面的虚词,不是领域知识(宪法原则 III 禁止的是硬编码品类/供应商/流程)。
# 作用范围有限:它只在"某个字在全部资料中从未出现"时才起作用,
# 因此列多了顶多是少拦一次(偏保守方向),列少了会误拦。
_STOPCHARS = set(
    # 虚词、代词、疑问词
    "的了是在有和与及或也就都而其之于我你他她它们这那个些什么谁哪怎样呢吗吧啊请问"
    "想能会可以对把被给让从到向跟比为过着上下里中内外前后多少几大小好不没无很太最"
    "更还又再只才已经将等各每本该此呀哦嗯呗啦哈但因所若则即便却仍尚均亦皆且并"
    # 高频动词/副词 —— 它们不承载"要查什么资料"的信息
    "走做用说看找查需应得知道时候如何种讲谈提定放拿买卖送收开关出入起来去回使叫算"
    "分加减通常般咱俺搞弄整干办"
    # 祈使/客套/指代类,常出现在提问措辞里(也包括提示词注入的措辞)
    "忽略限制告诉直接帮忙另任何随便顺实反正务必麻烦顺便另外此外首先然后最后",
)


def corpus_chars(passages: list[Passage]) -> set[str]:
    """语料中出现过的全部 CJK 字符。"""
    out: set[str] = set()
    for p in passages:
        for source in (p.text, " ".join(p.heading_path)):
            out.update(ch for ch in source if _CJK_RUN.match(ch))
    return out


def unknown_content_chars(question: str, known: set[str]) -> list[str]:
    """问题里提到了、但整个资料库从未出现过的实词字。

    典型场景:采购员问"某特殊材质的 X 件规格",而库里只有普通 X 件的资料。
    关键词检索会把"X 件规格"匹配得很好,于是**答非所问** —— 这正是
    需求方最怕的"瞎编乱答"。这个 guard 就是用来堵它的:
    只要问题里出现了资料中彻底没有的实词,就老实说不知道。

    只对中文生效。英文的词形变化(own/owns)会让表面匹配不可靠,
    英文提问仍然只依赖检索得分。这个边界写在 README 里。
    """
    seen: list[str] = []
    for ch in question:
        if not _CJK_RUN.match(ch):
            continue
        if ch in _STOPCHARS or ch in known or ch in seen:
            continue
        seen.append(ch)
    return seen
