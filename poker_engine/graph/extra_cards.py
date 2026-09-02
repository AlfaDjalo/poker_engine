"""
poker_engine/graph/extra_cards.py

Extra Card mechanics: ESG, Catchup ESG, Christmas, and Grinch.

All four are variations on one primitive -- "deal N extra hold cards to
eligible players before the next street, IF some condition holds" --
so they share a single AUTO handler (deal_extra_hole_card) rather than
four bespoke ones. Only the *condition* differs per mode; the actual
card movement is identical for all four (round-robin DECK -> HAND,
exactly like deal_hole_cards).

Usable directly as a flow step:

    - id: esg_check_turn
      type: deal_extra_hole_card
      config:
        mode: esg
        count: 1
        eligible: active
      metadata: {street_index: -1, street_name: esg}

Modes
-----
esg
    Triggered iff len(discard_pile) >= len(remaining_players) at the
    moment this node runs. Re-evaluated fresh every time this node is
    reached -- no memory across streets.

catchup_esg
    Same trigger condition as esg, OR'd with a "missed last time"
    flag (state.decisions["catchup_esg_pending"]) recorded by this
    same handler the previous time it ran and the condition was
    false. Once triggered (either because the live condition held, or
    because a prior miss is being caught up), the pending flag is
    cleared. This does not model "N misses queued up" -- only whether
    the *most recent* check went unfulfilled -- which is enough to
    express "caught up on the first future street with enough
    discards" for the common one-miss-then-catch-up case.

    NOTE: per the design note calling it a placeholder, there is no
    "cards that will be undealt after the river are added to the
    discard pile early" logic yet -- discard_pile only grows via
    ordinary FOLD/CARD_SELECT moves, so catchup_esg and esg trigger on
    the same streets until that placeholder is filled in.

christmas
    Triggered iff deck_remaining_count >= remaining_board_cards +
    len(remaining_players), where `remaining_board_cards` is a
    config-supplied constant: the number of board cards still to be
    dealt across the REST of the hand as of this check (not just the
    upcoming street). This is a fact about the variant's own flow
    shape (known at YAML-authoring time), so it's supplied by the flow
    author rather than derived at runtime.

grinch_christmas
    Triggered iff state.decisions[grinch_decision_key] is truthy --
    that key is expected to have been recorded by an upstream `type:
    boolean, decider: last_aggressor` DECISION step (see
    flow_loader.py / decision_domains/boolean_choice.py). This mode
    does no threshold math of its own; it's a pure DecisionFlag read,
    kept as its own mode (rather than composing a raw
    ExtraValue/DecisionFlag condition inline) so a variant's flow
    reads declaratively ("mode: grinch_christmas") instead of
    spelling out a condition by hand.
"""

from typing import List

from poker_engine.cards.mask import mask_to_card_ids
from poker_engine.graph.card_move import CardMove, CardMoveExecutor
from poker_engine.graph.core_types import CardZone, ZoneRef
from poker_engine.graph.node import Node

_MODES = ("esg", "catchup_esg", "christmas", "grinch_christmas")


def _eligible_players(kind: str, state) -> List[int]:
    if kind == "active":
        return state.active_players()
    if kind == "remaining":
        return state.remaining_players()
    raise ValueError(f"deal_extra_hole_card: unknown eligible kind {kind!r}")


def _deck_remaining_count(deck) -> int:
    return sum(1 for _ in mask_to_card_ids(deck.remaining_mask()))


def _is_triggered(node: Node, engine) -> bool:
    state = engine.state
    mode = node.config.get("mode")

    if mode == "esg":
        return len(state.discard_pile) >= len(state.remaining_players())

    if mode == "catchup_esg":
        live = len(state.discard_pile) >= len(state.remaining_players())
        pending = bool(state.decisions.get("catchup_esg_pending", False))
        triggered = live or pending
        state.record_decision("catchup_esg_pending", not triggered)
        return triggered

    if mode == "christmas":
        remaining_board = node.config["remaining_board_cards"]
        needed = remaining_board + len(state.remaining_players())
        return _deck_remaining_count(engine.deck) >= needed

    if mode == "grinch_christmas":
        key = node.config["grinch_decision_key"]
        return bool(state.decisions.get(key, False))

    raise ValueError(
        f"deal_extra_hole_card: unknown/missing mode {mode!r} "
        f"(expected one of {_MODES})"
    )


def handle_deal_extra_hole_card(engine, node: Node) -> dict:
    """
    AUTO handler for auto_type == "deal_extra_hole_card". Registered
    into graph_engine.AUTO_HANDLERS and flow_loader._STANDARD_AUTO_TYPES
    (see those modules' small registration patches) so it's usable
    directly as a `flow:` step type.

    config:
      mode                    -> "esg" | "catchup_esg" | "christmas" |
                                  "grinch_christmas" (required)
      count                   -> extra cards dealt per eligible player
                                  when triggered (default 1)
      eligible                -> "active" (default) or "remaining"
      remaining_board_cards   -> required for "christmas"
      grinch_decision_key     -> required for "grinch_christmas"

    Returns {"extra_card_triggered": bool} as this node's own
    ConditionContext.extra, in case a variant ever wants a transition
    to branch on whether the deal actually happened; not needed for
    the common "always continue to the next street regardless" case,
    which is why every extra-card YAML below just chains this step to
    the next one unconditionally.
    """
    state = engine.state
    triggered = _is_triggered(node, engine)

    if triggered:
        count = node.config.get("count", 1)
        eligible = _eligible_players(node.config.get("eligible", "active"), state)
        executor = CardMoveExecutor()
        for _ in range(count):
            for p in eligible:
                move = CardMove(
                    source=ZoneRef(CardZone.DECK),
                    destination=ZoneRef(CardZone.HAND, p),
                    count=1,
                )
                executor.execute(move, state, engine.deck)

    state.record_decision(f"{node.id}:triggered", triggered)
    return {"extra_card_triggered": triggered}