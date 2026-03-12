"""
Suit isomorphism utilities.

Canonicalizes suits across board + hole cards so
strategically identical states collapse to one.
"""

from typing import Dict, List, Tuple

from cards.mask import mask_to_card_ids, card_to_mask

# ---------------------------------------------------------
# Card utilities
# ---------------------------------------------------------

def card_rank(card_id: int) -> int:
    return card_id % 13


def card_suit(card_id: int) -> int:
    return card_id // 13


def make_card(rank: int, suit: int) -> int:
    return suit * 13 + rank


# ---------------------------------------------------------
# Generator wrapper
# ---------------------------------------------------------

def compute_suit_map(mask: int) -> Dict[int, int]:
    """
    Determine canonical suit mapping based on first appearance.
    """

    suit_map: Dict[int, int] = {}
    next_suit = 0

    for card in sorted(mask_to_card_ids(mask), key=card_rank):

        s = card_suit(card)

        if s not in suit_map:
            suit_map[s] = next_suit
            next_suit += 1

        return suit_map
    

# ---------------------------------------------------------
# Apply mapping
# ---------------------------------------------------------

def apply_suit_map(mask: int, suit_map: Dict[int, int]) -> int:
    """
    Apply suit mapping to a mask.
    """

    new_mask = 0

    for card in mask_to_card_ids(mask):

        r = card_rank(card)
        s = card_suit(card)

        new_suit = suit_map.get(s, s)

        new_card = make_card(r, new_suit)

        new_mask |= card_to_mask(new_card)

    return new_mask


# ---------------------------------------------------------
# Board canonicalization
# ---------------------------------------------------------

def canonicalize_board(board_mask: int) -> int:
    """
    Canonicalize board suits.
    """

    suit_map = compute_suit_map(board_mask)

    return apply_suit_map(board_mask, suit_map)


# ---------------------------------------------------------
# Full state canonicalization
# ---------------------------------------------------------

def canonicalize_state(
        hole_masks: List[int],
        board_mask: int
) -> Tuple[List[int], int]:
    """
    Canonicalize board + hole cards together.
    
    Returns:
        canonical_hole_masks
        canonical_board_mask
    """

    combined_mask = board_mask
    
    for h in hole_masks:
        combined_mask |= h
    
    suit_map = compute_suit_map(combined_mask)

    new_board = apply_suit_map(board_mask, suit_map)

    new_holes = [
        apply_suit_map(h, suit_map)
        for h in hole_masks
    ]

    return new_holes, new_board



# ---------------------------------------------------------
# Generator wrapper
# ---------------------------------------------------------

# def unique_canonical_masks(masks: Iterable[int]) -> Iterable[int]:
#     """
#     Yield masks while removing suit-isomorphic duplicates.
#     """

#     seen = set()

#     for mask in masks:
        
#         canon = canonicalize_mask(mask)

#         if canon in seen:
#             continue

#         seen.add(canon)

#         yield mask