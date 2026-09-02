"""
poker_engine/graph/decision_domains/card_pass.py

CARD_PASS DecisionDomainResolver -- pass the trash.

Each eligible player chooses exactly `count` cards from their own hand to
send to a target resolved by a fixed rule (currently "left"/"right" --
adjacent-seat passing; add more rules here as needed, e.g. a specific
seat offset). The player only ever chooses WHICH cards; the recipient is
never a choice.

Simultaneity, and why apply() doesn't move cards immediately:
Pass-the-trash is a blind, simultaneous exchange -- every player chooses
without seeing what anyone else passed or received. If each player's
cards were moved into their target's hand_mask the moment that player
decided, a player who acts later in turn order would see extra cards
already sitting in their hand before making their OWN selection, which
is wrong. So apply() only *records* the intended (card_ids, target) pair
per player (via state.record_decision, under a node-scoped key) and
advances the round; nothing physically moves yet. Once every eligible
player has acted (RoundComplete), the graph is expected to route through
an AUTO node with auto_type == "distribute_passes" (config:
{"decision_node": <this node's id>}), whose handler calls
execute_pending_passes() below to apply every recorded pass at once, only
then removing cards from senders' hands and adding them to recipients'.

Node config:
  count          -> exact number of cards to pass (required)
  target_rule    -> "left" (default) or "right", resolved against
                     len(state.players); "left" = seat (actor+1) % n.
  eligible        -> "active" (default) or "remaining" -- same meaning
                     and same all-in caveat as card_select.py.
"""

from typing import Any, Dict, List, Tuple

from poker_engine.graph.card_move import CardMove, CardMoveExecutor
from poker_engine.graph.core_types import (
    CardPassOption,
    CardZone,
    DecisionDomain,
    DecisionRequest,
    DecisionResponse,
    ZoneRef,
)
from poker_engine.graph.decision_domains.base import DecisionDomainResolver
from poker_engine.graph.node import Node

_PENDING_KEY_PREFIX = "__pending_pass__"


class CardPassResolver(DecisionDomainResolver):

    domain = DecisionDomain.CARD_PASS

    def build_request(self, node: Node, state, deck) -> DecisionRequest:
        if node.decider != "current_player":
            raise ValueError(
                f"CARD_PASS node {node.id!r} must have decider='current_player', "
                f"got {node.decider!r}"
            )

        player = self._current_actor(node, state)
        target = self._resolve_target(node, state, player)
        option = CardPassOption(
            source=ZoneRef(CardZone.HAND, player),
            target=ZoneRef(CardZone.HAND, target),
            count=node.config["count"],
        )
        return DecisionRequest(node_id=node.id, domain=self.domain, player_index=player, options=(option,))

    def validate(self, node: Node, state, deck, response: DecisionResponse) -> None:
        super().validate(node, state, deck, response)

        card_ids = response.value
        request = self.build_request(node, state, deck)
        option = request.options[0]

        if len(card_ids) != option.count:
            raise ValueError(f"Must pass exactly {option.count} cards, got {len(card_ids)}")
        if len(set(card_ids)) != len(card_ids):
            raise ValueError("Duplicate cards in selection")

        player_state = state.players[option.source.index]
        for c in card_ids:
            if not (player_state.hand_mask & (1 << c)):
                raise ValueError(f"Card {c} is not in player {option.source.index}'s hand")

    def apply(self, node: Node, state, deck, response: DecisionResponse) -> None:
        self.validate(node, state, deck, response)

        request = self.build_request(node, state, deck)
        option = request.options[0]
        player = option.source.index

        # Deliberately deferred -- see module docstring. Executed all at
        # once by execute_pending_passes() after the round completes.
        key = f"{_PENDING_KEY_PREFIX}:{node.id}:{player}"
        state.record_decision(key, (tuple(response.value), option.target.index))
        state.mark_acted(player)

        eligible = self._eligible_players(node, state)
        if not all(state.has_acted(p) for p in eligible):
            state.advance_turn()

    # -----------------------------------------------------

    def _eligible_players(self, node: Node, state):
        kind = node.config.get("eligible", "active")
        return state.active_players() if kind == "active" else state.remaining_players()

    def _current_actor(self, node: Node, state) -> int:
        eligible = self._eligible_players(node, state)
        if state.current_player not in eligible:
            raise ValueError(
                f"CARD_PASS node {node.id!r}: current_player {state.current_player} "
                f"is not eligible ({eligible}) -- engine invariant violated"
            )
        return state.current_player

    def _resolve_target(self, node: Node, state, actor: int) -> int:
        rule = node.config.get("target_rule", "left")
        n = len(state.players)
        if rule == "left":
            return (actor + 1) % n
        if rule == "right":
            return (actor - 1) % n
        raise ValueError(f"Unknown CARD_PASS target_rule: {rule!r}")


def execute_pending_passes(node_id: str, state, deck) -> None:
    """
    Applies every CARD_PASS decision recorded at `node_id`, simultaneously,
    once its round is complete. Meant to be called by the graph engine's
    AUTO handler for auto_type == "distribute_passes"
    (config: {"decision_node": node_id}) -- see module docstring.

    Order among the pending passes doesn't matter for correctness: each
    pass removes cards from one player's hand and adds them to another's,
    and a player's own outgoing cards were already fixed at decision time
    (chosen from their pre-exchange hand), so passes can't interfere with
    each other regardless of application order.
    """
    prefix = f"{_PENDING_KEY_PREFIX}:{node_id}:"
    pending: List[Tuple[str, Tuple[Tuple[int, ...], int]]] = [
        (key, value) for key, value in state.decisions.items() if key.startswith(prefix)
    ]

    executor = CardMoveExecutor()
    for key, (card_ids, target_index) in pending:
        player = int(key[len(prefix):])
        move = CardMove(
            source=ZoneRef(CardZone.HAND, player),
            destination=ZoneRef(CardZone.HAND, target_index),
            card_ids=card_ids,
        )
        executor.execute(move, state, deck)
        del state.decisions[key]