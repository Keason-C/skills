"""渠道无关的内核(宪法原则 VI / contracts/core-api.md)。

CLI 和将来的企业微信适配器都只通过 ``AskService.ask`` 使用系统。
``ask`` 不打印、不读环境变量、不碰 argv —— 身份只能作为参数传进来。

``ask`` 的调用顺序本身就是契约(CA-5),其中最关键的一条:
**authz.partition 必须早于 prompting.build_request。**
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import authz, conflict, prompting, verifier
from .audit import AuditLog
from .errors import UnknownRequesterError  # noqa: F401  (re-export for callers)
from .escalation import EscalationStore
from .ingest.loader import (
    DEFAULT_SECRET_DIR,
    IndexData,
    build_index,
    load_index,
    save_index,
)
from .llm.base import LLMDriver
from .models import (
    Answer,
    AnswerStatus,
    AuditRecord,
    Citation,
    EscalationReason,
    GapReport,
    IngestReport,
    RejectedFile,
    Requester,
    Sensitivity,
)
from .retrieval import corpus_chars, score, unknown_content_chars
from .roster import Roster, detect_category, load_roster

EXCERPT_CHARS = 200

# INV-A4:拒答文案是**固定常量**,不随命中内容变化,防止通过文案差异侧信道推断内容。
DENIED_TEXT = "该问题涉及受限信息,你当前的权限无法查看。"
UNKNOWN_TEXT = "资料里没有查到相关内容,我不能凭猜测回答。"
EMPTY_CORPUS_TEXT = "知识库中暂无资料。"


@dataclass
class AskService:
    index: IndexData
    roster: Roster
    driver: LLMDriver
    state_dir: Path
    top_k: int = prompting.DEFAULT_TOP_K

    # -- 构造 ---------------------------------------------------------------

    @staticmethod
    def build_index(
        corpus_root: Path | str,
        state_dir: Path | str,
        *,
        secret_dir_name: str = DEFAULT_SECRET_DIR,
    ) -> IngestReport:
        index = build_index(corpus_root, secret_dir_name=secret_dir_name)
        path = save_index(index, state_dir)
        internal = [d for d in index.documents if d.sensitivity is Sensitivity.INTERNAL]
        restricted = [
            d for d in index.documents if d.sensitivity is Sensitivity.RESTRICTED
        ]
        by_cat: dict[str, int] = {}
        for d in restricted:
            by_cat[d.category or "(未归品类)"] = by_cat.get(d.category or "(未归品类)", 0) + 1
        return IngestReport(
            documents=len(index.documents),
            passages=len(index.passages),
            internal_docs=len(internal),
            restricted_docs=len(restricted),
            restricted_by_category=dict(sorted(by_cat.items())),
            rejected=index.rejected,
            index_path=str(path),
        )

    @classmethod
    def load(
        cls,
        corpus_root: Path | str,
        roster_path: Path | str,
        state_dir: Path | str,
        driver: LLMDriver,
        *,
        secret_dir_name: str = DEFAULT_SECRET_DIR,  # noqa: ARG003 - 保留以对齐契约
        top_k: int = prompting.DEFAULT_TOP_K,
    ) -> AskService:
        return cls(
            index=load_index(state_dir),
            roster=load_roster(roster_path),
            driver=driver,
            state_dir=Path(state_dir),
            top_k=top_k,
        )

    # -- 辅助 ---------------------------------------------------------------

    @property
    def _escalations(self) -> EscalationStore:
        return EscalationStore(self.state_dir)

    @property
    def _audit(self) -> AuditLog:
        return AuditLog(self.state_dir)

    @property
    def known_categories(self) -> frozenset[str]:
        """品类词表 = 名单里的 + 保密子目录里的。来自数据,不硬编码(原则 III)。"""
        from_docs = {d.category for d in self.index.documents if d.category}
        return frozenset(self.roster.categories | from_docs)

    # -- 唯一问答入口 -------------------------------------------------------

    def ask(self, question: str, employee_id: str) -> Answer:
        requester = self.roster.lookup(employee_id)  # 未知工号 → 抛异常(CA-6)
        now = datetime.now(timezone.utc)

        # ① 权限先于内容 —— 必须在检索与组 prompt 之前
        part = authz.partition(self.index, requester)

        if not self.index.passages:
            return self._abstain(question, requester, now, text=EMPTY_CORPUS_TEXT)

        # ② 未知词 guard:问题里提到了**整个库**(含看不见的部分)都没有的东西
        #    → 那就是真没有,老实说不知道。
        #
        #    放在权限判定**之前**是有意的:否则"某个库里根本没有的品类的框架协议"这种问题,
        #    会因为偶然蹭到某份保密文件的字眼而被答成"你权限不足",既误导人,
        #    又暗示"存在这么一份保密资料"。这里用全库字表,所以不泄露任何内容,
        #    只反映"确实一个字都没有"。
        unknown = unknown_content_chars(
            question, corpus_chars(part.visible + part.restricted)
        )
        if unknown:
            return self._abstain(
                question,
                requester,
                now,
                text=f"{UNKNOWN_TEXT}(「{''.join(unknown)}」在现有资料中从未出现过)",
            )

        probe = authz.restricted_hit_probe(question, part, self.index)

        # ③ 只在可见片段上检索
        scored = score(question, part.visible, self.index.idf)

        # ④ 命中了受限材料、且比可见材料更相关 → 明确告知权限不足
        visible_top = scored[0].score if scored else 0.0
        if probe.hit and probe.top_score > visible_top:
            return self._deny(question, requester, probe, now)

        if not scored:
            return self._abstain(question, requester, now, restricted_hit=probe.hit)

        # ⑤ 同主题多版本的裁决(需求方定的规则)
        groups = conflict.detect_groups(scored, self.index)
        demoted = conflict.demoted_doc_ids(groups)
        usable = [sp for sp in scored if sp.passage.doc_id not in demoted] or scored

        # ⑥ 组 prompt(此时受限内容早已不在)
        request, partial = prompting.build_request(
            question, usable, self.index, self.top_k
        )

        # ⑦ 调模型 —— 驱动异常不得炸到调用方(CA-7)
        try:
            response = self.driver.generate(request)
        except Exception:  # noqa: BLE001
            return self._abstain(question, requester, now, restricted_hit=probe.hit)

        # ⑧ 不信任模型:确定性校验
        result = verifier.check(request, response)
        if not result.ok:
            return self._abstain(
                question,
                requester,
                now,
                restricted_hit=probe.hit,
                fabrication_blocked=result.fabrication_blocked,
                partial_context=partial,
            )

        # ⑨ 出处由代码生成 —— 模型无法伪造一个好看的假引用(D-05)
        by_pid = {sp.passage.passage_id: sp for sp in usable}
        citations = tuple(
            Citation(
                passage_id=pid,
                doc_name=self.index.docs_by_id[by_pid[pid].passage.doc_id].filename,
                locator=by_pid[pid].passage.locator,
                excerpt=by_pid[pid].passage.text[:EXCERPT_CHARS],
            )
            for pid in result.cited_ids
            if pid in by_pid
        )
        if not citations:  # 兜底:没有出处就不是答案(INV-A1)
            return self._abstain(question, requester, now, restricted_hit=probe.hit)

        # ⑩ FR-005b:比不出新旧的冲突来源必须**并列摆出**,机器人不许硬挑一个。
        answer_text = response.answer_text.strip()
        cited_docs = {c.passage_id.split("#")[0] for c in citations}
        parallel = [
            g
            for g in groups
            if g.resolution == "unresolved" and cited_docs & set(g.doc_ids)
        ]
        if parallel:
            extra: list[Citation] = []
            for g in parallel:
                for did in g.doc_ids:
                    if did in cited_docs:
                        continue
                    top = next(
                        (sp for sp in usable if sp.passage.doc_id == did), None
                    )
                    if top is None:
                        continue
                    cited_docs.add(did)
                    extra.append(
                        Citation(
                            passage_id=top.passage.passage_id,
                            doc_name=self.index.docs_by_id[did].filename,
                            locator=top.passage.locator,
                            excerpt=top.passage.text[:EXCERPT_CHARS],
                        )
                    )
            if extra:
                citations = citations + tuple(extra)
                answer_text = (
                    "资料中有多处相关说明,内容不一致,请自行核实后再执行。"
                    "以下为全部来源,系统不做裁决。"
                )

        # 只对**真正支撑了本次答案**的冲突组发提示。否则"某文档的新旧两版"这种
        # 弱命中会在每个不相干的问题下面挂一条"另有旧版",纯噪声。
        relevant = [
            g
            for g in groups
            if cited_docs & set(g.doc_ids) or (g.primary_doc_id in cited_docs)
        ]
        groups = relevant
        notices = list(conflict.notices_for(groups, self.index))
        if partial:
            notices.append(
                f"资料较多,本次只参考了其中相关度最高的 {len(request.passages)} 段。"
            )

        answer = Answer(
            status=AnswerStatus.ANSWERED,
            text=answer_text,
            citations=citations,
            notices=tuple(notices),
            conflicts=tuple(groups),
            partial_context=partial,
        )
        self._write_audit(
            question, requester, answer, now, probe.hit, [c.passage_id for c in citations]
        )
        return answer

    # -- 分支 ---------------------------------------------------------------

    def _contacts(self, question: str, probe_categories: frozenset[str] = frozenset()):
        category = detect_category(question, self.known_categories)
        if category is None and len(probe_categories) == 1:
            category = next(iter(probe_categories))
        return category, self.roster.route_for(category)

    def _deny(self, question, requester, probe, now) -> Answer:
        if probe.uncategorised:
            # 未归品类的保密材料只有采购负责人能处理,转给品类经理等于白转
            category, contacts = None, self.roster.fallback
        else:
            category, contacts = self._contacts(question, probe.categories)
        esc = self._escalations.create(
            requester=requester,
            question=question,
            reason=EscalationReason.PERMISSION_DENIED,
            question_category=category,
            routed_to=contacts,
            now=now,
        )
        answer = Answer(
            status=AnswerStatus.DENIED,
            text=DENIED_TEXT,  # 固定文案(INV-A4)
            contacts=contacts,
            escalation_id=esc.escalation_id,
        )
        self._write_audit(question, requester, answer, now, True, [])
        return answer

    def _abstain(
        self,
        question,
        requester,
        now,
        *,
        text: str = UNKNOWN_TEXT,
        restricted_hit: bool = False,
        fabrication_blocked: bool = False,
        partial_context: bool = False,
    ) -> Answer:
        category, contacts = self._contacts(question)
        reason = (
            EscalationReason.FABRICATION_BLOCKED
            if fabrication_blocked
            else EscalationReason.NO_COVERAGE
        )
        esc = self._escalations.create(
            requester=requester,
            question=question,
            reason=reason,
            question_category=category,
            routed_to=contacts,
            now=now,
        )
        answer = Answer(
            status=AnswerStatus.UNKNOWN,
            text=text,
            contacts=contacts,
            escalation_id=esc.escalation_id,
            partial_context=partial_context,
            fabrication_blocked=fabrication_blocked,
        )
        self._write_audit(question, requester, answer, now, restricted_hit, [])
        return answer

    def _write_audit(
        self, question, requester: Requester, answer: Answer, now, restricted_hit, pids
    ) -> None:
        doc_ids = sorted({pid.split("#")[0] for pid in pids})
        self._audit.append(
            AuditRecord(
                at=now,
                employee_id=requester.employee_id,
                role=requester.role,
                question=question,
                status=answer.status,
                visible_hit_doc_ids=tuple(doc_ids),  # 只可能是可见文档
                restricted_hit=bool(restricted_hit),  # 只记布尔(INV-U1)
                fabrication_blocked=answer.fabrication_blocked,
                partial_context=answer.partial_context,
                escalation_id=answer.escalation_id,
            )
        )

    # -- 报表 ---------------------------------------------------------------

    def gaps(self, limit: int = 50) -> GapReport:
        return self._escalations.gap_report(limit)

    def rejected(self) -> tuple[RejectedFile, ...]:
        return self.index.rejected

    def audit_tail(self, limit: int = 50) -> tuple[AuditRecord, ...]:
        return self._audit.tail(limit)
