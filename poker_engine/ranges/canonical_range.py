from typing import Dict, Iterable

from cards.mask import mask_to_card_ids
from cards.suit_iso import canonicalize_state


def canonicalize_hand(mask: int) -> int:
    """
    Canonicalize a single hand mask.
    """
    holes, _ = canonicalize_state([mask], 0)
    return holes[0]


def build_canonical_range(hole_masks: Iterable[int]) -> Dict[int, int]:
    """
    Compress a set of raw hole-card masks into canonical
    masks with multiplicity weights.
    
    Returns:
        {canonical_mask: weight}
    """

    result: Dict[int, int] = {}

    for mask in hole_masks:

        canon = canonicalize_hand(mask)

        result[canon] = result.get(canon, 0) + 1

    return result