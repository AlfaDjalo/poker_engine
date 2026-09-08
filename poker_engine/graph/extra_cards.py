"""
poker_engine/graph/extra_cards.py

Extra Card mechanics: ESG, Catchup ESG, Christmas, and Grinch.

All four are variations on one primitive -- "deal N extra hold cards to
eligible players before the next street, IF some condition holds" --
so they share a single AUTO handler (deal_extra_hole_card) rather than
four bespoke ones. Only the *condition* differs per mode, AND (see
"Card source by mode" below) which ZONE the cards are dealt FROM; the
"deal N cards to each eligible player" movement pattern itself is
otherwise identical for all four.

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
    Tracks a running "owed" counter (state.decisions
    ["catchup_esg_owed"]) of extra-cards-per-player that SKIPPED
    checks have accumulated so far. Only a check that itself SKIPS
    (doesn't deal) ever adds to the total; the check that finally
    deals discharges the WHOLE backlog exactly as it stands, with
    nothing added on top for itself -- it is, by definition, not one
    of the skips being recovered.

    Two cases, evaluated every time this check runs:

      owed > 0 (there's an existing backlog):
        needed = owed * len(eligible). If the discard pile currently
        holds at least that many cards, trigger and deal exactly
        `owed` cards to each eligible player -- paying off every
        street that skipped so far, all at once -- and reset owed to
        0. Otherwise, THIS check also skips: owed is increased by this
        check's own `count` (base_count) and carried forward.

      owed == 0 (no backlog yet):
        Behaves exactly like plain "esg" for this one check: trigger
        and deal `count` cards iff len(discard_pile) >=
        len(remaining_players()). If that's not met, this check
        starts a fresh backlog of `count`.

    Worked example (count=1 every check, two consecutive skips then a
    paying street): check 1 skips -> owed 0->1. Check 2 skips (still
    can't cover even owed=1) -> owed 1->2. Check 3's discard pile can
    now cover 2*eligible -> it deals exactly 2 cards per eligible
    player (recovering both of the prior skips together) and owed
    resets to 0 -- not 3, and not capped at 1.

    This also stays safe for a hand where nobody ever folds/discards
    at all (discard pile stays empty all hand): every check just keeps
    accumulating `owed` and never triggers, rather than forcing a deal
    the pile can't back (see each branch's feasibility gate, and the
    ValueError safety net in handle_deal_extra_hole_card below, which
    should now be unreachable for this mode precisely because that
    gate exists).

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
    boolean, decider: persistent_last_aggressor` DECISION step (see
    flow_loader.py / decision_domains/boolean_choice.py /
    graph_state.py's persistent_last_aggressor). This mode does no
    threshold math of its own; it's a pure DecisionFlag read, kept as
    its own mode (rather than composing a raw ExtraValue/DecisionFlag
    condition inline) so a variant's flow reads declaratively ("mode:
    grinch_christmas") instead of spelling out a condition by hand.

Card source by mode
--------------------
ESG and Catchup ESG are, by definition, a MUCK-recycling mechanic --
players get dealt cards FROM THE DISCARD PILE, never fresh cards from
the deck. Christmas and Grinch, by contrast, deal genuinely fresh cards
FROM THE DECK. Both used to unconditionally source from CardZone.DECK,
which was wrong for the two ESG modes (it let a discard-recycling
mechanic hand out cards nobody had ever discarded, and left the
discard pile never actually shrinking the way the mechanic's own name
implies). _DISCARD_SOURCED_MODES below is what the handler consults to
route correctly.

Sourcing from the discard pile also shuffles state.discard_pile in
place immediately beforehand, so which discarded card a given eligible
player ends up with isn't deterministic on fold/discard order.

If a discard-sourced mode triggers needing more cards than are
currently in the discard pile, this raises ValueError rather than
silently falling back to the deck -- that's a variant/authoring bug
(the trigger condition and the eligible-player count disagreed about
how many cards are actually available), not something to paper over at
deal time.
"""

import random
from typing import List

from poker_engine.cards.mask import mask_to_card_ids
from poker_engine.graph.card_move import CardMove, CardMoveExecutor
from poker_engine.graph.core_types import CardZone, ZoneRef
from poker_engine.graph.node import Node

_MODES = ("esg", "catchup_esg", "christmas", "grinch_christmas")

# Modes that deal from the MUCK (discard pile), never the deck. See
# module docstring, "Card source by mode".
_DISCARD_SOURCED_MODES = {"esg", "catchup_esg"}


def _eligible_players(kind: str, state) -> List[int]:
    if kind == "active":
        return state.active_players()
    if kind == "remaining":
        return state.remaining_players()
    raise ValueError(f"deal_extra_hole_card: unknown eligible kind {kind!r}")


def _deck_remaining_count(deck) -> int:
    return sum(1 for _ in mask_to_card_ids(deck.remaining_mask()))


def _is_triggered(node: Node, engine):
    """
    Returns (triggered: bool, deal_count: int) -- deal_count is how
    many extra cards THIS check should deal to each eligible player if
    triggered. For every mode except catchup_esg, deal_count is always
    just node.config["count"] (or 1). catchup_esg is the one mode
    where deal_count can exceed that -- see its own branch, and the
    module docstring's "catchup_esg" section for the accumulating-debt
    rule this implements.
    """
    state = engine.state
    mode = node.config.get("mode")
    base_count = node.config.get("count", 1)

    if mode == "esg":
        triggered = len(state.discard_pile) >= len(state.remaining_players())
        return triggered, base_count

    if mode == "catchup_esg":
        eligible = _eligible_players(node.config.get("eligible", "active"), state)
        owed = int(state.decisions.get("catchup_esg_owed", 0))

        if owed > 0:
            # Existing backlog: this check can either fully discharge
            # it (paying exactly `owed`, nothing added for itself --
            # it's not a skip), or -- if the pile still can't cover
            # even that -- it ALSO skips, growing the backlog by its
            # own base_count.
            needed = owed * len(eligible)
            if len(state.discard_pile) >= needed:
                state.record_decision("catchup_esg_owed", 0)
                return True, owed
            state.record_decision("catchup_esg_owed", owed + base_count)
            return False, 0

        # No backlog yet: identical to plain esg for this one check.
        live = len(state.discard_pile) >= len(state.remaining_players())
        if live:
            return True, base_count
        state.record_decision("catchup_esg_owed", base_count)
        return False, 0

    if mode == "christmas":
        remaining_board = node.config["remaining_board_cards"]
        needed = remaining_board + len(state.remaining_players())
        triggered = _deck_remaining_count(engine.deck) >= needed
        return triggered, base_count

    if mode == "grinch_christmas":
        key = node.config["grinch_decision_key"]
        triggered = bool(state.decisions.get(key, False))
        return triggered, base_count

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
                                  when triggered (default 1). For
                                  catchup_esg specifically this is only
                                  the PER-CHECK baseline increment --
                                  the actual number dealt on a
                                  triggering street can be a multiple
                                  of it, once accumulated misses are
                                  paid off together (see module
                                  docstring, "catchup_esg").
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
    mode = node.config.get("mode")
    triggered, count = _is_triggered(node, engine)

    if triggered:
        eligible = _eligible_players(node.config.get("eligible", "active"), state)
        executor = CardMoveExecutor()

        if mode in _DISCARD_SOURCED_MODES:
            # ESG/Catchup ESG redeal cards FROM the muck -- that's the
            # whole point of the mechanic (recycling discards), not a
            # deck draw. See module docstring, "Card source by mode".
            if state.discard_pile is None:
                state.discard_pile = []
            random.shuffle(state.discard_pile)

            needed = count * len(eligible)
            if needed > len(state.discard_pile):
                raise ValueError(
                    f"{node.id!r}: mode {mode!r} triggered needing "
                    f"{needed} discard-pile card(s) but only "
                    f"{len(state.discard_pile)} are available"
                )
            source_zone = CardZone.DISCARD_PILE
        else:
            source_zone = CardZone.DECK

        for _ in range(count):
            for p in eligible:
                move = CardMove(
                    source=ZoneRef(source_zone),
                    destination=ZoneRef(CardZone.HAND, p),
                    count=1,
                )
                executor.execute(move, state, engine.deck)

    state.record_decision(f"{node.id}:triggered", triggered)
    return {"extra_card_triggered": triggered}