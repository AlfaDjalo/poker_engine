import random
from .mask import card_to_mask, mask_to_card_ids

FULL_DECK_MASK = (1 << 52) - 1

class Deck:
    __slots__ = ("_mask", "_draw_order")

    def __init__(self):
        self._mask = FULL_DECK_MASK
        self._draw_order = list(range(52))

    def shuffle(self):
        """Reset deck to full and randomize draw order."""
        self._mask = FULL_DECK_MASK
        self._draw_order = list(range(52))
        random.shuffle(self._draw_order)

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