import random
from .mask import card_to_mask, mask_to_card_ids

FULL_DECK_MASK = (1 << 52) - 1

class Deck:
    __slots__ = ("_mask", "_draw_order")

    def __init__(self):
        self._mask = FULL_DECK_MASK
        self._draw_order = list(range(52))

    def shuffle(self):
        """Reset deck to full and randomize draw order. Used at the
        start of a new HAND -- NOT for reshuffling discards mid-hand,
        since that would wrongly resurrect cards currently live in
        hands/on the board. See reshuffle_remaining() for that case."""
        self._mask = FULL_DECK_MASK
        self._draw_order = list(range(52))
        random.shuffle(self._draw_order)

    def reshuffle_remaining(self):
        """
        Shuffle the draw order of whatever cards are CURRENTLY still in
        the deck (self._mask), without touching which cards are
        in/out of the deck. Call this after returning discard-pile
        cards to the deck via return_card() -- it randomizes their
        position among the deck's existing remaining cards, rather
        than resetting to a full 52-card deck (which would be wrong
        mid-hand: cards are still live in hole cards/on the board).
        """
        remaining = list(mask_to_card_ids(self._mask))
        random.shuffle(remaining)
        self._draw_order = remaining

    def remove(self, card_id: int):
        self._mask &= ~(1 << card_id)

    def draw_random(self) -> int:
        available = list(mask_to_card_ids(self._mask))
        card = random.choice(available)
        self.remove(card)
        return card
    
    def draw_next(self) -> int:
        """Draw the next card from the shuffled deck."""
        for card_id in self._draw_order:
            if self._mask & (1 << card_id):
                self.remove(card_id)
                return card_id
        raise RuntimeError("No cards remaining in deck")
    
    def remaining_mask(self) -> int:
        return self._mask

    def remaining_count(self) -> int:
        return bin(self._mask).count("1")
    
    def return_card(self, card_id: int):
        """Return a card to the deck (used when reshuffling discard pile)."""
        self._mask |= (1 << card_id)
