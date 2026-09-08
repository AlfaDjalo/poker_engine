"""
poker_engine/graph/decision_domains/betting.py

BETTING DecisionDomainResolver.

Wires the graph engine to the existing, already-correct betting-sizing
logic in poker_engine.actions.betting_rules.BettingRules (NoLimitRules /
PotLimitRules / FixedLimitRules / AllInOrFoldRules) instead of
duplicating it. This is the piece that finally makes that module live
code: per its own docstring it was previously an unused reference spec,
with GameState.legal_actions()/apply_action() reimplementing similar but
thinner betting-type branching inline. Once the graph engine is the only
execution path, that inline branching in GameState becomes dead and
should be deleted (see graph_state.py's note on this).

A BETTING node is a multi-player round like any other round domain, but
its round-completion tracking reuses GameState's own mature
apply_action()/betting_round_complete()/advance_turn() machinery (side
pots, all-ins, the "one player left with chips who hasn't matched yet"
edge case, etc.) rather than the generic round_acted mechanism other
domains use -- see condition.BettingRoundComplete, which a BETTING
node's forward transition is expected to use.

Node config:
  node.config["rules"]  -> a BettingRules instance (required). This is
                           per-node, not a single fixed setting for the
                           whole variant -- a variant could (if it ever
                           needed to) use FixedLimitRules pre-flop/flop
                           and NoLimitRules on later streets, simply by
                           giving different BET nodes different `rules`.
  node.decider            -> must be "current_player" for BETTING nodes:
                             the decider is always whoever
                             GameState.current_player is, since
                             apply_action()/advance_turn() are what keep
                             that pointer correct across the round.

Known gap (not addressed here): the legacy "river_only" betting_type in
GameState (a single pot-sized bet, no re-raises ever) has no matching
BettingRules subclass yet -- AllInOrFoldRules already covers push-fold,
but river_only would need a new, small BettingRules subclass. That's an
additive task (write one more BettingRules subclass) whenever it's
needed, not a change to this resolver or the graph engine.

Persistent (cross-street) last-aggressor tracking
--------------------------------------------------
Every real BET/RAISE also records the acting player as the graph
state's PERSISTENT last aggressor (GraphGameState.persistent_last_aggressor,
via state.record_aggressor()) -- distinct from GameState.last_aggressor,
which reset_betting_round() clears every street. This is a generic
primitive (any future mechanic needing "who bet/raised last, falling
back across streets" reads it), not something scoped to Grinch, which
is simply its first consumer. The other end of the fallback chain --
seeding it from the forced bets (BB, or first ante-poster if there are
no blinds) at the start of a hand -- lives in graph_engine.py's
handle_post_blinds/handle_post_antes.
"""

from poker_engine.actions.action import Action
from poker_engine.actions.action_type import ActionType
from poker_engine.graph.core_types import (
    BettingOption,
    DecisionDomain,
    DecisionRequest,
    DecisionResponse,
)
from poker_engine.graph.decision_domains.base import DecisionDomainResolver
from poker_engine.graph.node import Node


class BettingResolver(DecisionDomainResolver):

    domain = DecisionDomain.BETTING

    def build_request(self, node: Node, state, deck) -> DecisionRequest:
        if node.decider != "current_player":
            raise ValueError(
                f"BETTING node {node.id!r} must have decider='current_player', "
                f"got {node.decider!r}"
            )

        rules = node.config["rules"]
        actions = rules.legal_actions(state)

        if not actions:
            raise ValueError(
                f"BETTING node {node.id!r}: no legal actions for current player "
                f"{state.current_player} -- the engine should not have entered "
                f"this node for a folded/all-in player"
            )

        # BettingRules.legal_actions() returns two Action entries for a
        # sizeable BET/RAISE -- one at the minimum size, one at the
        # maximum (see betting_rules.py) -- rather than a single ranged
        # option. Collapse same-type entries into one BettingOption with
        # a min/max span, so a DecisionRequest always has exactly one
        # option per distinct choice being offered.
        spans = {}
        order = []
        for a in actions:
            if a.type not in spans:
                spans[a.type] = [a.amount, a.amount]
                order.append(a.type)
            else:
                lo, hi = spans[a.type]
                spans[a.type] = [min(lo, a.amount), max(hi, a.amount)]

        options = tuple(
            BettingOption(action_type=t, min_amount=spans[t][0], max_amount=spans[t][1])
            for t in order
        )

        return DecisionRequest(
            node_id=node.id,
            domain=self.domain,
            player_index=state.current_player,
            options=options,
        )

    def validate(self, node: Node, state, deck, response: DecisionResponse) -> None:
        super().validate(node, state, deck, response)

        action = response.value
        if not isinstance(action, Action):
            raise ValueError(f"BETTING response.value must be an Action, got {type(action)!r}")

        request = self.build_request(node, state, deck)
        matching = next((o for o in request.options if o.action_type == action.type), None)
        if matching is None:
            raise ValueError(f"Action type {action.type} is not legal at node {node.id!r}")
        if not (matching.min_amount <= action.amount <= matching.max_amount):
            raise ValueError(
                f"Action amount {action.amount} outside legal range "
                f"[{matching.min_amount}, {matching.max_amount}] for {action.type}"
            )

    def apply(self, node: Node, state, deck, response: DecisionResponse) -> dict:
        self.validate(node, state, deck, response)

        action: Action = response.value
        actor = state.current_player

        state.apply_action(action)
        state.record_decision(f"{node.id}:last_action", action)

        if action.type in (ActionType.BET, ActionType.RAISE):
            # Persists across streets -- see module docstring and
            # GraphGameState.record_aggressor(). Every caller running
            # the graph engine uses a GraphGameState, so this attribute
            # is always present.
            state.record_aggressor(actor)

        # Snapshot completion BEFORE advancing current_player. GameState.
        # betting_round_complete()'s "turn has cycled back to last_to_act"
        # check is only meaningful evaluated once, immediately after the
        # action that was just applied; re-evaluating it live after
        # advance_turn() has already moved current_player would give a
        # false positive the instant current_player first cycles around
        # to equal last_to_act, even though that player hasn't acted yet
        # this round. Handing the snapshot to the transition layer via
        # `extra` (see condition.BettingRoundComplete) avoids that.
        complete = state.betting_round_complete()
        if not complete:
            state.advance_turn()

        return {"betting_round_complete": complete}
