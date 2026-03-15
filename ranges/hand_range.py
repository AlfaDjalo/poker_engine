from dataclasses import dataclass
from typing import Dict, Iterable, Tuple

from cards.mask import mask_to_card_ids


@dataclass
class RangeEntry:
    """
    One canonical hand in a range.
    """

    mask: int
    weight: float


class HandRange:
    """
    Solver-grade compressed range representation.
    
    Stores canonical hand masks with weights.
    """

    def __init__(self):

        self.entries: Dict[int, RangeEntry] = {}

    def add(self, mask: int, weight: float = 1.0):

        if mask in self.entries:
            self.entries[mask].weight += weight
        else:
            self.entries[mask] = RangeEntry(mask, weight)

    def remove_blocked(self, board_mask: int):
        """
        Remove hands that collide with board cards.
        """

        board_cards = set(mask_to_card_ids(board_mask))

        to_delete = []

        for mask, entry in self.entries.items():

            cards = mask_to_card_ids(mask)

            if any(c in board_cards for c in cards):
                to_delete.append(mask)

        for m in to_delete:
            del self.entries[m]

    def normalize(self):

        total = sum(e.weight for e in self.entries.values())

        if total == 0:
            return
    
        for e in self.entries.values():
            e.weight /= total

    def __iter__(self):

        return iter(self.entries.values())
    
    def __len__(self):

        return len(self.entries)