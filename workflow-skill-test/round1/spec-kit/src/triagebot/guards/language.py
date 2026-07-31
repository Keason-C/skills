"""Language detection and the unsupported-language cap (task T017).

Detection is deliberately coarse (spec.md -> Assumptions): it distinguishes "contains
Chinese", "plausibly English", and "neither". That is sufficient because the "neither"
branch is not handled by a bespoke rule -- it is routed to a human by the *existing*
confidence guard, via the cap applied here (FR-032).

The cap lives here rather than inside a driver so that it applies to every driver, including
the Anthropic one. A rule that only the mock enforced would not be a rule.
"""

from __future__ import annotations

import re

from ..models import ClassificationProposal, GuardFinding, GuardRule, Language
from ..settings import TriageSettings

_CJK = re.compile(r"[一-鿿㐀-䶿]")
_LATIN_LETTER = re.compile(r"[A-Za-z]")
#: Scripts that are neither Latin nor Han: Hiragana/Katakana, Hangul, Cyrillic, Arabic,
#: Hebrew, Devanagari, Thai, Greek.
_OTHER_SCRIPT = re.compile(
    r"[぀-ヿ가-힯Ѐ-ӿ؀-ۿ"
    r"֐-׿ऀ-ॿ฀-๿Ͱ-Ͽ]"
)


def detect_language(text: str) -> Language:
    """Classify ``text`` as English, Chinese, or neither (FR-031, FR-032).

    A non-Latin, non-Han script anywhere in the text wins: Japanese prose containing a few
    kanji must not be mistaken for Chinese, so kana is checked before Han.
    """
    if _OTHER_SCRIPT.search(text):
        return Language.OTHER
    if _CJK.search(text):
        return Language.ZH
    if _LATIN_LETTER.search(text):
        return Language.EN
    return Language.OTHER


def language_guard(
    proposal: ClassificationProposal,
    language: Language,
    settings: TriageSettings,
) -> tuple[ClassificationProposal, GuardFinding | None]:
    """Force category ``OTHER`` and cap confidence for unsupported languages (FR-032).

    Pure: returns a new proposal rather than mutating the input.
    """
    if language is not Language.OTHER:
        return proposal, None

    capped = min(proposal.confidence, settings.unsupported_language_confidence_cap)
    if proposal.category is Language.OTHER and capped == proposal.confidence:
        return proposal, None

    from ..models import Category  # local import keeps the module header short

    adjusted = proposal.model_copy(
        update={"category": Category.OTHER, "confidence": capped}
    )
    finding = GuardFinding(
        rule=GuardRule.UNSUPPORTED_LANGUAGE,
        field="category",
        proposed=proposal.category.value,
        final=Category.OTHER.value,
        detail=(
            "Ticket is written in neither English nor Chinese; categorised OTHER and "
            f"confidence capped at {settings.unsupported_language_confidence_cap} so the "
            "confidence guard routes it to a human."
        ),
    )
    return adjusted, finding
