"""领域异常。"""

from __future__ import annotations


class ProcurementBotError(Exception):
    """本项目所有异常的基类。"""


class CorpusNotFoundError(ProcurementBotError):
    """语料目录不存在或不可读。"""


class IndexMissingError(ProcurementBotError):
    """尚未执行 ingest,索引文件不存在。"""


class UnknownRequesterError(ProcurementBotError):
    """工号不在人员名单中。

    注意:这里**故意抛异常而不是降级为最小权限**。静默降级会把权限问题变成
    "某人突然查不到东西"的玄学故障,排查成本极高(research.md D-10)。
    """


class RosterFormatError(ProcurementBotError):
    """人员名单格式错误。消息中必须包含行号,方便非技术用户自己改。"""


class UnsupportedFormatError(ProcurementBotError):
    """文件格式不受支持。会被 loader 捕获并转成 RejectedFile,不会中断导入。"""


class ParseError(ProcurementBotError):
    """文件损坏或无法解析。同上,会被转成 RejectedFile。"""
