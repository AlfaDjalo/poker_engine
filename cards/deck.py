import random
from .mask import card_to_mask, mask_to_card_ids

FULL_DECK_MASK = (1 << 52) - 1

class Deck:
    __slots__ = ("_mask",)

    def __init__(self):
        self._mask = FULL_DECK_MASK

    def remove(self, card_id: int):
        self._mask &= ~(1 << card_id)

    def draw_random(self) -> int:
        available = list(mask_to_card_ids(self._mask))
        card = random.choice(available)
        self.remove(card)
        return card
    
    def remaining_mask(self) -> int:
        return self._mask