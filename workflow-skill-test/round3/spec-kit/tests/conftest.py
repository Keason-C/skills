"""共享测试夹具。

**最重要的东西在最上面**:禁网 fixture。

宪法原则 IV 要求"测试套件 MUST 全部离线可跑"。一句约定是不够的——只要有人不小心
在测试里引入了真实调用,测试可能仍然"通过",然后我们就得到了一个依赖运气的测试套件。
所以这里把 socket 连接直接打断:任何测试一旦尝试联网,会立刻抛异常而不是悄悄成功。
"""

from __future__ import annotations

import socket
from datetime import date
from pathlib import Path

import pytest

from procurement_bot.core import AskService
from procurement_bot.llm.mock import KeywordMockDriver


class NetworkAccessInTestsError(RuntimeError):
    """测试中尝试联网时抛出。"""


def _blocked(*args, **kwargs):  # noqa: ANN002, ANN003
    raise NetworkAccessInTestsError(
        "测试禁止联网(宪法原则 IV)。真实 LLM 驱动只写不跑;"
        "如果你看到这个错误,说明有代码试图发起网络请求。"
    )


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """自动应用到每一个测试:切断一切出网路径。"""
    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)


# --------------------------------------------------------------------------
# 语料与名单夹具
# --------------------------------------------------------------------------

ROSTER_CSV = """工号,姓名,角色,负责品类
P1001,李明,采购员,
P1002,张伟,品类经理,电解铜
P1003,王芳,品类经理,紧固件
P1005,赵强,品类经理,电解铜;铝锭
P9000,陈国华,采购负责人,*
"""

# 受限文档里的这个价格串,被 test_authz 用来断言"它绝不会出现在任何下游产物中"。
SECRET_PRICE = "68500"


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    """一份小而全的文本语料,覆盖:普通/受限、有日期冲突/无日期冲突。"""
    root = tmp_path / "corpus"

    write(
        root / "品类管理手册-电解铜.md",
        "# 电解铜品类管理手册\n\n"
        "## 品类归属\n\n"
        "本品类负责人:张伟(工号 P1002),分机 8021。\n\n"
        "## 规格要求\n\n"
        "电解铜执行 Cu-CATH-1 标准,含铜量不低于 99.95%。\n",
    )
    write(
        root / "供应商准入流程.txt",
        "供应商准入流程\n"
        "第一步 资质初审,第二步 现场审核,第三步 样品检测,第四步 列入合格供应商清单。\n",
    )
    # 两份互相矛盾且都没有日期 —— 触发 FR-005b(并列展示)
    write(
        root / "规格要求-紧固件.md",
        "# 紧固件规格要求\n\n## 表面处理\n\n紧固件表面处理采用达克罗。\n",
    )
    write(
        root / "规格要求-紧固件-补充.md",
        "# 紧固件规格要求补充\n\n## 表面处理\n\n紧固件表面处理一律采用镀锌钝化。\n",
    )
    # 两份带生效日期的同主题文档 —— 触发 FR-005a(取新 + 注明旧版)
    write(
        root / "采购流程说明.md",
        "# 采购流程说明\n\n生效日期:2024-03-01\n\n## 审批环节\n\n审批流程共三级:主管、经理、总监。\n",
    )
    write(
        root / "采购流程说明-2019旧版.md",
        "# 采购流程说明\n\n生效日期:2019-05-01\n\n## 审批环节\n\n审批流程共五级。\n",
    )
    # 受限:电解铜
    write(
        root / "保密" / "电解铜" / "成本构成说明.md",
        "# 电解铜成本构成\n\n## 采购单价\n\n"
        f"2025 年协议采购单价为 {SECRET_PRICE} 元/吨,其中加工费 1200 元/吨。\n",
    )
    # 受限:紧固件
    write(
        root / "保密" / "紧固件" / "谈判策略要点.md",
        "# 紧固件谈判策略\n\n## 底线\n\n谈判底线为年降 5%,可让步至 3%。\n",
    )
    # 受限:未归品类(保密根目录)—— 只有采购负责人能看
    write(
        root / "保密" / "集团年度成本目标.md",
        "# 集团年度成本目标\n\n全集团年度采购降本目标为 7.2%。\n",
    )
    return root


@pytest.fixture
def roster_path(tmp_path: Path) -> Path:
    p = tmp_path / "roster.csv"
    p.write_text(ROSTER_CSV, encoding="utf-8")
    return p


@pytest.fixture
def service(corpus: Path, roster_path: Path, tmp_path: Path) -> AskService:
    state = tmp_path / ".pbot"
    AskService.build_index(corpus, state)
    return AskService.load(
        corpus_root=corpus,
        roster_path=roster_path,
        state_dir=state,
        driver=KeywordMockDriver(),
    )


@pytest.fixture
def today() -> date:
    return date(2026, 7, 31)
