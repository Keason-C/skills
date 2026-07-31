"""生成演示用的**合成假采购文档**。

⚠️ 这里造出来的每一个字都是编的:假供应商、假价格、假条款。
真实文档一份都还没拿到(业主暂时给不了脱敏样例),所以演示语料只能自己造。
别把它当成真数据,更别拿里面的"报价"去跟谁谈判。

跑法:uv run python scripts/make_demo_corpus.py
"""

from __future__ import annotations

import csv
import shutil
from pathlib import Path

from docgen import write_docx, write_pdf, write_scanned_pdf, write_text, write_xlsx

ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE = ROOT / "demo" / "knowledge"
ROSTER = ROOT / "demo" / "roster.csv"


def build() -> None:
    if KNOWLEDGE.exists():
        shutil.rmtree(KNOWLEDGE)

    # --- 金属 --------------------------------------------------------------
    write_docx(
        KNOWLEDGE / "金属" / "金属品类策略2024.docx",
        [
            "金属品类采购策略(2024 版)",
            "生效日期:2024-01-01",
            "一、总体策略",
            "本品类采用双供应商策略(dual sourcing),主供应商份额不超过 70%,备供应商不低于 20%。",
            "二、框架协议",
            "年度框架协议一年一签,每年 11 月启动次年谈判,12 月 15 日前完成签署。",
            "三、付款条件",
            "标准账期为月结 60 天(NET 60),新供应商首年为月结 30 天。",
            "四、准入要求",
            "供应商须持有 ISO9001 与 IATF16949 认证,并通过现场审核(on-site audit)。",
        ],
    )
    write_text(
        KNOWLEDGE / "金属" / "金属品类策略(旧版).md",
        "# 金属品类采购策略\n\n生效日期:2021-04-01\n\n"
        "本品类采用**单一供应商策略**,以换取更高的量价折让。\n\n"
        "标准账期为月结 30 天(NET 30)。\n\n"
        "> 说明:此版本已被 2024 版取代,保留供追溯。\n",
    )
    write_xlsx(
        KNOWLEDGE / "金属" / "金属合格供应商名录.xlsx",
        [
            ["供应商名称", "英文名", "所在地", "资质", "准入状态", "主供品项"],
            ["华兴金属制造", "Huaxing Metal Mfg.", "江苏无锡", "ISO9001/IATF16949", "合格", "冷轧板"],
            ["ACME 金属", "ACME Metals Ltd", "广东东莞", "ISO9001", "合格", "型材、管件"],
            ["恒通精密", "Hengtong Precision", "浙江宁波", "ISO9001", "试用", "紧固件"],
        ],
        "合格供应商",
    )

    # --- 包材 --------------------------------------------------------------
    write_pdf(
        KNOWLEDGE / "包材" / "瓦楞纸箱规格书.pdf",
        [
            "瓦楞纸箱规格书 / Corrugated Carton Specification",
            "生效日期: 2023-11-15",
            "1. 材质 Material: AA 级三层瓦楞 / 3-ply corrugated board",
            "2. 边压强度 Edge Crush Test (ECT): >= 32 lb/in",
            "3. 耐破强度 Bursting Strength: >= 250 kPa",
            "4. 印刷 Printing: 水性油墨 water-based ink, 不得含重金属",
            "5. 抽检比例 AQL: 一般缺陷 II 级 / General Level II",
            "6. 包装标识: 须含料号 Part No.、批次 Lot No.、生产日期",
        ],
    )
    write_docx(
        KNOWLEDGE / "包材" / "包材品类策略.docx",
        [
            "包材品类采购策略",
            "生效日期:2024-05-20",
            "本品类以就近供货为原则,运输半径不超过 300 公里,以压缩物流成本。",
            "常规料号保持三家合格供应商,季度询价一次(quarterly RFQ)。",
            "包装材料须符合客户端的可回收要求(recyclable),供应商需提供材质证明。",
        ],
    )

    # --- 电子件 ------------------------------------------------------------
    write_pdf(
        KNOWLEDGE / "电子件" / "连接器规格书 Connector Spec.pdf",
        [
            "连接器规格书 / Connector Specification",
            "生效日期: 2024-06-10",
            "Pitch: 2.54 mm, Current rating: 3 A per contact",
            "Operating temperature: -40 C to +105 C",
            "阻燃等级 Flame rating: UL94 V-0",
            "环保要求: RoHS 3 & REACH compliant, 须提供第三方报告",
            "替代料 Alternative parts 须经研发与品类经理双签方可使用。",
        ],
    )

    # --- 流程 --------------------------------------------------------------
    write_text(
        KNOWLEDGE / "流程" / "请购与审批流程.md",
        "# 请购与审批流程\n\n生效日期:2024-02-01\n\n"
        "1. 需求部门在系统提交请购单(PR),写明料号、数量、需求日期。\n"
        "2. 品类经理审核技术规格与供应商选择。\n"
        "3. 金额 5 万元以下由采购经理审批;5 万至 50 万由采购总监审批;"
        "50 万以上须报总经理审批。\n"
        "4. 审批通过后由采购员下达采购订单(PO)。\n"
        "5. 收货后三个工作日内完成入库与三单匹配(PO / 收货单 / 发票)。\n",
    )
    write_text(
        KNOWLEDGE / "流程" / "新人常见问题.txt",
        "问:框架协议去哪里查?\n答:在合同管理系统的「框架协议」目录下,按品类检索。\n\n"
        "问:供应商要变更银行账号怎么办?\n"
        "答:必须由供应商用盖章的正式函件提出,财务与采购双人核实,不接受邮件口头变更。\n\n"
        "问:紧急采购能不能先发货后补单?\n"
        "答:不可以。紧急件走加急审批通道,但仍须先有 PO。\n",
    )

    # --- 保密文件夹:整份保密(ADR-0005) --------------------------------
    write_xlsx(
        KNOWLEDGE / "保密" / "金属" / "2024金属供应商报价单.xlsx",
        [
            ["供应商", "料号", "单价(元/吨)", "年度折扣", "阶梯价起订量(吨)"],
            ["华兴金属制造", "MTL-1001", "4820", "3.0%", "50"],
            ["ACME 金属", "MTL-1001", "4950", "1.5%", "30"],
            ["恒通精密", "MTL-2044", "6180", "0.0%", "10"],
        ],
        "2024报价",
    )
    write_docx(
        KNOWLEDGE / "保密" / "包材" / "包材谈判策略与纪要.docx",
        [
            "包材品类谈判策略与纪要(内部,禁止外传)",
            "生效日期:2024-04-08",
            "一、我方底价",
            "瓦楞纸箱目标价 2.10 元/平米,底价 2.25 元/平米,首轮报价从 2.60 元起谈。",
            "二、对手情况",
            "供应商 A 上季度产能利用率约 六成,议价空间较大;供应商 B 有独家花色,慎用压价。",
            "三、让步节奏",
            "第一轮不让价,第二轮以延长账期换单价,第三轮才动量价折让。",
        ],
    )
    write_xlsx(
        KNOWLEDGE / "保密" / "电子件" / "电子件成本拆解.xlsx",
        [
            ["料号", "材料成本", "加工费", "管理费摊销", "测算总成本", "当前采购价"],
            ["CON-3301", "1.82", "0.44", "0.19", "2.45", "3.10"],
            ["CON-3302", "2.05", "0.51", "0.21", "2.77", "3.48"],
        ],
        "成本测算",
    )

    # --- 读不进来的两类 ----------------------------------------------------
    write_scanned_pdf(KNOWLEDGE / "合同" / "2022框架协议扫描件.pdf")
    (KNOWLEDGE / "杂项").mkdir(parents=True, exist_ok=True)
    (KNOWLEDGE / "杂项" / "旧系统导出.dat").write_bytes(b"\x00\x01\x02\x03 legacy export blob")

    # --- 人员名单 ----------------------------------------------------------
    ROSTER.parent.mkdir(parents=True, exist_ok=True)
    with ROSTER.open("w", encoding="utf-8", newline="") as fh:
        csv.writer(fh).writerows(
            [
                ["工号", "姓名", "角色", "负责品类", "联系方式"],
                ["1001", "李强", "采购员", "", "liqiang@example.com"],
                ["1002", "周涛", "采购员", "", "zhoutao@example.com"],
                ["2001", "王敏", "品类经理", "金属;电子件", "wangmin@example.com"],
                ["2002", "赵磊", "品类经理", "包材", "zhaolei@example.com"],
                ["9001", "陈静", "品类经理", "", "chenjing@example.com"],
            ]
        )

    files = sorted(p for p in KNOWLEDGE.rglob("*") if p.is_file())
    print(f"演示语料已生成:{KNOWLEDGE}({len(files)} 个文件)")
    for path in files:
        print(f"  {path.relative_to(KNOWLEDGE)}")
    print(f"人员名单:{ROSTER}")


if __name__ == "__main__":
    build()
