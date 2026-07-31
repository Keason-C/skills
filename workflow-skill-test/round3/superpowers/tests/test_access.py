from pathlib import Path

from pkbot.access import owners_for_category, partition
from pkbot.models import (
    CONFIDENTIAL,
    PUBLIC,
    ROLE_ADMIN,
    ROLE_BUYER,
    ROLE_CATEGORY_MANAGER,
    Document,
    Library,
    Section,
    User,
)


def _doc(doc_id, classification, category=None):
    return Document(
        doc_id, doc_id, Path(doc_id), classification, category, (Section("全文", "内容"),)
    )


LIB = Library(
    documents=(
        _doc("public/流程.md", PUBLIC),
        _doc("confidential/紧固件/纪要.md", CONFIDENTIAL, "紧固件"),
        _doc("confidential/电子元器件/报价.md", CONFIDENTIAL, "电子元器件"),
        _doc("confidential/未分类.md", CONFIDENTIAL, None),
    ),
    unreadable=(),
)


def test_buyer_sees_only_public():
    v = partition(User("G1", "李四", ROLE_BUYER, ()), LIB)
    assert {d.doc_id for d in v.visible} == {"public/流程.md"}
    assert len(v.hidden) == 3


def test_manager_sees_only_own_categories():
    v = partition(User("G2", "王五", ROLE_CATEGORY_MANAGER, ("紧固件",)), LIB)
    assert {d.doc_id for d in v.visible} == {
        "public/流程.md",
        "confidential/紧固件/纪要.md",
    }
    assert {d.doc_id for d in v.hidden} == {
        "confidential/电子元器件/报价.md",
        "confidential/未分类.md",
    }


def test_uncategorised_confidential_is_admin_only():
    admin = partition(User("G3", "赵六", ROLE_ADMIN, ()), LIB)
    assert len(admin.visible) == 4
    assert admin.hidden == ()


def test_owners_for_category():
    roster = {
        "G2": User("G2", "王五", ROLE_CATEGORY_MANAGER, ("紧固件",)),
        "G1": User("G1", "李四", ROLE_BUYER, ()),
    }
    assert owners_for_category(roster, "紧固件") == ("王五",)
    assert owners_for_category(roster, "不存在的品类") == ()
    assert owners_for_category(roster, None) == ()
