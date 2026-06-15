"""
Suit isomorphism utilities.

Canonicalizes suits across board + hole cards so
strategically identical states collapse to one.

Canonicalization rule (board-anchored):
  1. Scan board cards in rank order; assign canonical suit IDs in order of
     first appearance (suit 0, 1, 2, ...).
  2. Scan hole cards in rank order, extending the map for any new suits.

This guarantees that:
  - The board's suit map is fully determined by the board alone.
  - Two states that differ only by a suit permutation produce the same
    canonical representation, regardless of which hole cards are present.
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
# Core: build a suit map by scanning masks in priority order
# ---------------------------------------------------------

def compute_suit_map(mask: int) -> Dict[int, int]:
    """
    Determine canonical suit mapping based on first appearance,
    scanning cards in rank order.

    Use this for single-mask canonicalization (board only).
    For full state canonicalization use canonicalize_state() which
    scans board first, then holes.
    """

    return _build_suit_map_ordered(mask)

    # suit_map: Dict[int, int] = {}
    # next_suit = 0

    # for card in sorted(mask_to_card_ids(mask), key=card_rank):
    #     s = card_suit(card)
    #     if s not in suit_map:
    #         suit_map[s] = next_suit
    #         next_suit += 1

    # return suit_map


def _build_suit_map_ordered(*masks: int) -> Dict[int, int]:
    """
    Build a complete 4-suit map using structural invariants.
    Board-specific minimum ranks anchor the primary suit sorting to satisfy 
    independent board canonicalization rules.
    """
    suit_contents: Dict[int, List[Tuple[int, int]]] = {s: [] for s in range(4)}
    
    for mask_idx, mask in enumerate(masks):
        for card in mask_to_card_ids(mask):
            s = card_suit(card)
            r = card_rank(card)
            suit_contents[s].append((mask_idx, r))

    def suit_sort_key(suit_idx: int):
        items = suit_contents[suit_idx]
        
        # Separate board ranks (mask_idx == 0) and hole ranks (mask_idx > 0)
        board_ranks = [r for m_idx, r in items if m_idx == 0]
        hole_ranks = [r for m_idx, r in items if m_idx > 0]
        
        # --- Crucial Board-Anchored Tie-Breaker ---
        # 1. If the suit has board cards, its primary score is based on the lowest board rank.
        #    We map it to a high tier tier (2).
        # 2. If it has NO board cards but has hole cards, its primary score is based on the lowest hole rank.
        #    We map it to a middle tier (1).
        # 3. If it's completely empty, it gets a tier of (0).
        if board_ranks:
            tier = 2
            min_rank = min(board_ranks)
        elif hole_ranks:
            tier = 1
            min_rank = min(hole_ranks)
        else:
            tier = 0
            min_rank = 13  # High dummy value so it loses the reverse sort

        # Invert min_rank because sorted(..., reverse=True) is used
        min_rank_score = (tier, 13 - min_rank)

        # Build feature vectors for card counts / ranks per layer
        layer_features = []
        for mask_idx in range(len(masks)):
            ranks_in_layer = sorted([r for m_idx, r in items if m_idx == mask_idx], reverse=True)
            layer_features.append((len(ranks_in_layer), ranks_in_layer))
            
        return (min_rank_score, layer_features)

    # Sort raw suits (0, 1, 2, 3) descending
    sorted_suits = sorted(range(4), key=suit_sort_key, reverse=True)
    
    return {raw_suit: canonical_suit for canonical_suit, raw_suit in enumerate(sorted_suits)}
    # suit_map: Dict[int, int] = {}
    # next_suit = 0

    # for mask in masks:
    #     for card in sorted(mask_to_card_ids(mask), key=card_rank):
    #         s = card_suit(card)
    #         if s not in suit_map:
    #             suit_map[s] = next_suit
    #             next_suit += 1

    # if len(suit_map) < 4:
    #     all_raw_suits = [0, 1, 2, 3]
    #     unused_canonincal = [suit for suit in all_raw_suits if suit not in suit_map.values()]

    #     for s in all_raw_suits:
    #         if s not in suit_map:
    #             suit_map[s] = unused_canonincal.pop(0)

    # return suit_map


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
        new_suit = suit_map[s]  #suit_map.get(s, s)
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
    Canonicalize board + hole cards together, board-anchored.

    The suit map is built by scanning the board first (in rank order),
    then each hole mask (in rank order). This ensures:
      - The canonical board is identical to canonicalize_board(board_mask).
      - Two suit-isomorphic states always produce the same canonical form.

    Returns:
        canonical_hole_masks, canonical_board_mask
    """
    # Board anchors the suit map; holes extend it for any unseen suits.
    suit_map = _build_suit_map_ordered(board_mask, *hole_masks)

    new_board = apply_suit_map(board_mask, suit_map)
    new_holes = [apply_suit_map(h, suit_map) for h in hole_masks]

    return new_holes, new_board
