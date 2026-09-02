"""
poker_engine/graph/card_move.py

Generic card-movement primitive.

Every mechanic that relocates cards -- dealing hole cards, dealing board
cards, plain discarding, drawing, passing the trash, ESG/Christmas bonus
cards -- is expressed as one or more CardMove operations executed against
a small set of zones (see core_types.CardZone). This is deliberately the
*only* verb the engine has for moving cards: a CardMove doesn't know or
care whether it's satisfying an automatic DEAL node or the resolved
outcome of a CARD_SELECT/CARD_PASS decision, and no individual mechanic
gets bespoke engine code for *how* cards move -- only for *which* cards
move, and *when* (that "when"/"which" logic lives in the AUTO-node
handlers and decision-domain resolvers that build CardMove instances,
not here).

CardMoveExecutor is the single place that knows how each CardZone is
physically represented (hand_mask bitmasks, node_cards slots, the
discard_pile list, deck draw order). Every other module deals only in
ZoneRef / CardMove and never touches players[i].hand_mask or
state.node_cards directly.
"""

from dataclasses import dataclass
from typing import Optional, Tuple

from poker_engine.graph.core_types import CardZone, ZoneRef


@dataclass(frozen=True)
class CardMove:
    """
    A single declarative move of one or more cards from `source` to
    `destination`.

    Provide exactly one of:
      - card_ids: explicit cards to move (required when source is HAND,
        BOARD_NODE, or a specific-cards DISCARD_PILE move -- i.e.
        whenever the cards involved were chosen by a decision rather
        than drawn/taken in zone order).
      - count: how many cards to take from source in the zone's own
        order (DECK draws its next `count` cards in shuffle order;
        DISCARD_PILE takes its first `count` cards). Not valid for
        HAND or BOARD_NODE sources, which have no inherent "next card"
        ordering -- those always require explicit card_ids.

    A BOARD_NODE can only ever hold a single card, so any move
    targeting one must move exactly one card.
    """

    source: ZoneRef
    destination: ZoneRef
    card_ids: Optional[Tuple[int, ...]] = None
    count: Optional[int] = None

    def __post_init__(self):
        if self.card_ids is None and self.count is None:
            raise ValueError("CardMove requires either explicit card_ids or a count")
        if self.card_ids is not None and self.count is not None:
            if len(self.card_ids) != self.count:
                raise ValueError("card_ids length must match count when both are given")
        if self.source.zone in (CardZone.HAND, CardZone.BOARD_NODE) and self.card_ids is None:
            raise ValueError(f"{self.source.zone.name} source requires explicit card_ids")

        n = len(self.card_ids) if self.card_ids is not None else self.count
        if self.destination.zone == CardZone.BOARD_NODE and n != 1:
            raise ValueError("BOARD_NODE destination can only receive a single card")


class CardMoveExecutor:
    """
    Applies CardMove operations against a live GameState + Deck,
    mutating both in place and returning the concrete card ids moved
    (useful when a move was specified by `count` rather than explicit
    ids -- e.g. dealing draws unknown-until-drawn cards).
    """

    def execute(self, move: CardMove, state, deck) -> Tuple[int, ...]:
        card_ids = self._take_from_source(move, state, deck)
        self._add_to_destination(card_ids, move.destination, state, deck)
        return card_ids

    # -----------------------------------------------------
    # Source side: remove cards from their current zone
    # -----------------------------------------------------

    def _take_from_source(self, move: CardMove, state, deck) -> Tuple[int, ...]:
        zone = move.source.zone

        if zone == CardZone.DECK:
            if move.card_ids is not None:
                for c in move.card_ids:
                    deck.remove(c)
                return move.card_ids
            return tuple(deck.draw_next() for _ in range(move.count))

        if zone == CardZone.HAND:
            player = state.players[move.source.index]
            for c in move.card_ids:
                player.hand_mask &= ~(1 << c)
            return move.card_ids

        if zone == CardZone.BOARD_NODE:
            node = move.source.index
            existing = state.node_cards[node]
            if existing is None:
                raise ValueError(f"BOARD_NODE[{node}] has no card to move")
            if move.card_ids is not None and move.card_ids != (existing,):
                raise ValueError(
                    f"BOARD_NODE[{node}] holds card {existing}, "
                    f"but move specified card_ids={move.card_ids}"
                )
            state.node_cards[node] = None
            return (existing,)

        if zone == CardZone.DISCARD_PILE:
            if move.card_ids is not None:
                for c in move.card_ids:
                    state.discard_pile.remove(c)
                return move.card_ids
            taken = tuple(state.discard_pile[: move.count])
            del state.discard_pile[: move.count]
            return taken

        raise ValueError(f"Unhandled source zone: {zone}")

    # -----------------------------------------------------
    # Destination side: place cards into their new zone
    # -----------------------------------------------------

    def _add_to_destination(self, card_ids: Tuple[int, ...], destination: ZoneRef, state, deck):
        zone = destination.zone

        if zone == CardZone.HAND:
            player = state.players[destination.index]
            for c in card_ids:
                player.hand_mask |= 1 << c
            return

        if zone == CardZone.BOARD_NODE:
            node = destination.index
            if state.node_cards[node] is not None:
                raise ValueError(f"BOARD_NODE[{node}] is already occupied")
            state.node_cards[node] = card_ids[0]
            return

        if zone == CardZone.DISCARD_PILE:
            state.discard_pile.extend(card_ids)
            return

        if zone == CardZone.DECK:
            for c in card_ids:
                deck.return_card(c)
            return

        raise ValueError(f"Unhandled destination zone: {zone}")