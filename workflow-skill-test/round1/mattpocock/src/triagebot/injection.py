"""Injection Attempt detection — deterministic, table-driven, and applied before any Driver runs.

A model asked whether it is being attacked is itself attackable, so nothing here calls a model.
The scan does two things: it reports what it found, and it produces the *redacted* text that the
Driver is allowed to see. Injected lines never reach a Driver, and never reach a tool argument
(ADR-0003).
"""

from __future__ import annotations

from dataclasses import dataclass

REDACTION = "[redacted: instruction-like text removed]"

INJECTION_MARKERS: tuple[str, ...] = (
    # English
    "ignore previous instructions",
    "ignore all previous",
    "ignore the above",
    "disregard the above",
    "disregard your instructions",
    "disregard previous",
    "system prompt",
    "you are now",
    "act as an",
    "developer mode",
    "new instructions:",
    "set priority to",
    "mark this as resolved",
    "approve the refund automatically",
    "without human review",
    "as an ai",
    # Chinese
    "忽略之前的指令",
    "忽略以上",
    "忽略上面",
    "忽略前面的",
    "无视之前",
    "系统提示",
    "你现在是",
    "扮演一个",
    "开发者模式",
    "新的指令",
    "把优先级设为",
    "标记为已解决",
    "自动批准退款",
    "无需人工",
)


@dataclass(frozen=True, slots=True)
class InjectionScan:
    """What the scan found, and the text the Driver may see."""

    detected: bool
    markers: tuple[str, ...]
    redacted_subject: str
    redacted_body: str


def _redact(text: str) -> tuple[str, tuple[str, ...]]:
    kept: list[str] = []
    found: list[str] = []
    for line in text.splitlines():
        hits = [marker for marker in INJECTION_MARKERS if marker in line.lower()]
        if hits:
            found.extend(hits)
            kept.append(REDACTION)
        else:
            kept.append(line)
    redacted = "\n".join(kept).strip() or REDACTION
    return redacted, tuple(dict.fromkeys(found))


def scan_for_injection(subject: str, body: str) -> InjectionScan:
    """Scan a Ticket's text for instruction-like content aimed at the triage system."""
    redacted_subject, subject_markers = _redact(subject)
    redacted_body, body_markers = _redact(body)
    markers = tuple(dict.fromkeys(subject_markers + body_markers))
    return InjectionScan(
        detected=bool(markers),
        markers=markers,
        redacted_subject=redacted_subject,
        redacted_body=redacted_body,
    )
