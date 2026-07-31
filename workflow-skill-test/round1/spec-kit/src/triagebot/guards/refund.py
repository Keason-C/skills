"""Refund policy and terminal action guards (tasks T045, T046).

Three refund rules, all deterministic (FR-015, FR-016, FR-016a):

1. an action the policy does not permit is replaced by one it does;
2. a refund with no policy record escalates rather than being answered from the model's own
   knowledge;
3. a refund outside the policy window escalates -- a human says "no", the machine never
   issues an automated denial.

Plus one rule that is broader than refunds (FR-016b): the machine never *executes* a
terminal, money-moving or denial action. It may recommend one, but the ticket goes to a
human to carry it out.

Two decisions the spec left open, recorded here and in the README decision log:

* **No order reference on a refund ticket** -> the window cannot be verified, so the ticket
  escalates. Consistent with "the machine does not guess and does not say no" (analyze F3).
* **Order not yet delivered** -> the refund window has not started, so the ticket is inside
  it. Cancelling a not-yet-delivered order is the ordinary case, not an edge case.
"""

from __future__ import annotations

from ..models import (
    TERMINAL_ACTIONS,
    ActionKind,
    Category,
    ClassificationProposal,
    GuardFinding,
    GuardRule,
    OrderFound,
    PolicyFound,
    ToolContext,
)


def refund_policy_guard(
    context: ToolContext,
    proposal: ClassificationProposal,
    category: Category,
) -> tuple[ActionKind, list[GuardFinding]]:
    """Constrain a refund recommendation to the retrieved policy.

    Returns the action to use plus every finding that fired. Non-refund categories pass
    through untouched.
    """
    findings: list[GuardFinding] = []
    action = proposal.suggested_action

    if category is not Category.REFUND:
        return action, findings

    policy = context.policy

    # (2) No policy record -> escalate rather than invent one (FR-016).
    if policy is None or not isinstance(policy, PolicyFound):
        findings.append(
            GuardFinding(
                rule=GuardRule.REFUND_POLICY,
                field="escalated_to_human",
                proposed=action.value,
                final=ActionKind.ROUTE_TO_HUMAN.value,
                detail=(
                    "No refund policy record exists for this category; escalating rather "
                    "than answering from the model's own knowledge."
                ),
            )
        )
        return ActionKind.ROUTE_TO_HUMAN, findings

    # (1) Constrain the action to the policy's permitted set (FR-015).
    if action not in policy.permitted_actions:
        replacement = policy.permitted_actions[0]
        findings.append(
            GuardFinding(
                rule=GuardRule.REFUND_POLICY,
                field="recommended_action",
                proposed=action.value,
                final=replacement.value,
                detail=(
                    f"Suggested action {action.value} is not permitted by the refund "
                    f"policy; replaced with {replacement.value}. Policy: {policy.summary}"
                ),
            )
        )
        action = replacement

    # (3) Window check (FR-016a).
    order = context.order
    if not isinstance(order, OrderFound):
        findings.append(
            GuardFinding(
                rule=GuardRule.REFUND_POLICY,
                field="escalated_to_human",
                proposed="False",
                final="True",
                detail=(
                    "Refund requested but no verifiable order was found, so the refund "
                    "window cannot be checked; escalating for human verification."
                ),
            )
        )
        return action, findings

    days = order.days_since_delivery
    if days is not None and days > policy.window_days:
        findings.append(
            GuardFinding(
                rule=GuardRule.REFUND_POLICY,
                field="escalated_to_human",
                proposed="False",
                final="True",
                detail=(
                    f"Delivery was {days} days ago, outside the {policy.window_days}-day "
                    "refund window. Escalating so a human can decline or make an "
                    "exception; the system never issues an automated denial."
                ),
            )
        )

    return action, findings


def terminal_action_guard(action: ActionKind) -> GuardFinding | None:
    """Escalate any ticket whose recommended action moves money or denies a request.

    Applies to every category, not just refunds (FR-016b).
    """
    if action not in TERMINAL_ACTIONS:
        return None

    return GuardFinding(
        rule=GuardRule.TERMINAL_ACTION,
        field="escalated_to_human",
        proposed="False",
        final="True",
        detail=(
            f"Recommended action {action.value} is terminal: it moves money or denies a "
            "customer request. It is emitted as a recommendation, but a human executes it."
        ),
    )
