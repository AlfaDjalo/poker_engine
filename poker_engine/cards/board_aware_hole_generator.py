from typing import Iterable, List

from cards.mask import card_to_mask, mask_to_card_ids
from cards.suit_iso import compute_suit_map


RANKS = list(range(13))
MAX_SUITS = 4


def make_card(rank: int, suit: int) -> int:
    return suit * 13 + rank


def generate_board_aware_hole_masks(board_mask: int, num_hole_cards: int) -> Iterable[int]:
    """
    Generate canonical hole-card masks conditioned on a board.
    
    Ensures:
    - no overlap with board
    - canonical suit ordering anchored to board suits
    """

    board_cards = set(mask_to_card_ids(board_mask))

    suit_map = compute_suit_map(board_mask)

    used_suits = set(suit_map.values())

    next_suit = max(used_suits) + 1 if used_suits else 0

    hand: List[int] = []

    yield from _dfs(hand, board_cards, next_suit, num_hole_cards)


def _dfs(hand: List[int], board_cards: set, next_suit: int, target: int):

    if len(hand) == target:

        mask = 0
        for c in hand:
            mask |= card_to_mask(c)

            yield mask
            return
        
        used_suits = {c // 13 for c in hand}

        max_suit = max(used_suits) if used_suits else -1

        allowed_suits = max(max_suit + 2, next_suit)

        for rank in RANKS:

            for suit in range(min(allowed_suits, MAX_SUITS)):

                card = make_card(rank, suit)

                if card in board_cards:
                    continue

                hand.append(card)

                yield from _dfs(hand, board_cards, next_suit, target)

                hand.pop()