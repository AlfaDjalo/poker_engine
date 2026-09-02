"""
poker_engine/graph/decision_domains/card_select.py

CARD_SELECT DecisionDomainResolver -- discard and draw.

A single mechanic covers both: choose between min_count and max_count
cards from your own hand; if replace_from_deck is set, an equal number
of fresh cards are then dealt back into that hand (Draw), otherwise the
chosen cards simply leave play (plain Discard).

Unlike CARD_PASS (see card_pass.py), a CARD_SELECT decision only ever
touches the acting player's own hand -- it never depends on, or is
observed by, any other player's choice -- so it's safe to execute
immediately as each player decides, with no simultaneity staging needed.

Node config:
  min_count / max_count   -> legal size range for the selection
  replace_from_deck       -> bool, default False (Discard vs Draw)
  eligible                -> "active" (default; not folded, not all-in --
                              matches GameState.advance_turn()'s own skip
                              rule so turn order Just Works) or
                              "remaining" (not folded, INCLUDING all-in --
                              use only if the variant needs all-in
                              players to still select cards; note
                              GameState.advance_turn() does not currently
                              visit all-in players, so "remaining" alone
                              isn't sufficient for that yet -- flagging
                              as a known follow-up rather than solving it
                              here, to avoid scope creep into turn-order
                              mechanics unrelated to card selection itself).

decider must be "current_player": like BETTING, this is a rotating
multi-player round, tracked via the generic state.round_acted mechanism
(see condition.RoundComplete, which a CARD_SELECT node's forward
transition is expected to use).

Turn advancement within the round is DOMAIN-NATIVE (see
_next_unacted_player below) -- NOT GameState.advance_turn(). That method
is built for BETTING's own round-completion semantics
(bet_to_call/current_bet/last_to_act comparisons) and nothing resets
those fields for a non-betting round; reusing it here meant a
CARD_SELECT round's turn order was silently driven by whatever betting
state happened to be left over from the PRECEDING betting round,
varying hand to hand. _next_unacted_player instead walks seat order and
consults ONLY state.round_acted (this round's own completion tracking)
and this node's own `eligible` set -- nothing borrowed from betting.
"""

from poker_engine.graph.card_move import CardMove, CardMoveExecutor
from poker_engine.graph.core_types import (
    CardSelectOption,
    CardZone,
    DecisionDomain,
    DecisionRequest,
    DecisionResponse,
    ZoneRef,
)
from poker_engine.graph.decision_domains.base import DecisionDomainResolver
from poker_engine.graph.node import Node


class CardSelectResolver(DecisionDomainResolver):

    domain = DecisionDomain.CARD_SELECT

    def build_request(self, node: Node, state, deck) -> DecisionRequest:
        if node.decider != "current_player":
            raise ValueError(
                f"CARD_SELECT node {node.id!r} must have decider='current_player', "
                f"got {node.decider!r}"
            )

        player = self._current_actor(node, state)
        option = CardSelectOption(
            source=ZoneRef(CardZone.HAND, player),
            min_count=node.config["min_count"],
            max_count=node.config["max_count"],
            replace_from_deck=node.config.get("replace_from_deck", False),
        )
        return DecisionRequest(node_id=node.id, domain=self.domain, player_index=player, options=(option,))

    def validate(self, node: Node, state, deck, response: DecisionResponse) -> None:
        super().validate(node, state, deck, response)

        card_ids = response.value
        request = self.build_request(node, state, deck)
        option = request.options[0]

        if not (option.min_count <= len(card_ids) <= option.max_count):
            raise ValueError(
                f"Must select between {option.min_count} and {option.max_count} "
                f"cards, got {len(card_ids)}"
            )
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
        card_ids = tuple(response.value)

        executor = CardMoveExecutor()
        if card_ids:
            discard = CardMove(
                source=ZoneRef(CardZone.HAND, player),
                destination=ZoneRef(CardZone.DISCARD_PILE),
                card_ids=card_ids,
            )
            executor.execute(discard, state, deck)

            if option.replace_from_deck:
                draw = CardMove(
                    source=ZoneRef(CardZone.DECK),
                    destination=ZoneRef(CardZone.HAND, player),
                    count=len(card_ids),
                )
                executor.execute(draw, state, deck)

        state.record_decision(f"{node.id}:player_{player}_selected", card_ids)
        state.mark_acted(player)

        eligible = self._eligible_players(node, state)
        if not all(state.has_acted(p) for p in eligible):
            state.current_player = self._next_unacted_player(state, eligible)

    # -----------------------------------------------------

    def _eligible_players(self, node: Node, state):
        kind = node.config.get("eligible", "active")
        return state.active_players() if kind == "active" else state.remaining_players()

    def _next_unacted_player(self, state, eligible) -> int:
        """
        Domain-native replacement for GameState.advance_turn() -- see
        module docstring for why advance_turn() itself is unsafe here.

        Walks the full seat range (not just `eligible`'s own order) so
        SEAT POSITION determines visiting order, matching every other
        round-driving mechanism in this codebase
        (handle_set_first_to_act, reset_betting_round) -- `eligible`
        only filters WHO qualifies, not the order to visit them in.
        Consults ONLY state.round_acted (via state.has_acted) for
        completion -- no betting field is read or written.

        Returns state.current_player unchanged if every eligible
        player has already acted (RoundComplete should already be
        true by then and this branch should be unreached from apply()
        -- returning the current player rather than raising keeps this
        defensive instead of a hard crash if it's ever called after
        the fact).
        """
        n = len(state.players)
        current = state.current_player
        for offset in range(1, n + 1):
            candidate = (current + offset) % n
            if candidate in eligible and not state.has_acted(candidate):
                return candidate
        return current

    def _current_actor(self, node: Node, state) -> int:
        eligible = self._eligible_players(node, state)
        if state.current_player not in eligible:
            raise ValueError(
                f"CARD_SELECT node {node.id!r}: current_player {state.current_player} "
                f"is not eligible ({eligible}) -- engine invariant violated, the graph "
                f"engine should never have left the round pointed at a non-eligible player"
            )
        return state.current_player