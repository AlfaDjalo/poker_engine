from typing import Iterable, List

from cards.mask import card_to_mask


RANKS = list(range(13))
MAX_SUITS = 4


def make_card(rank: int, suit: int) -> int:
    return suit * 13 + rank


def generate_canonical_hole_masks(num_cards: int) -> Iterable[int]:
    """
    Generate canonical hole-card masks for any number of cards.
    """

    hand: List[int] = []

    yield from _dfs(hand, num_cards)


def _dfs(hand: List[int], target: int):
    
    if len(hand) == target:

        mask = 0
        for c in hand:
            mask |= card_to_mask(c)

        yield mask
        return

    used_suits = {c // 13 for c in hand}

    max_suit = max(used_suits) if used_suits else -1

    for rank in RANKS:

        for suit in range(max_suit + 2):

            if suit >= MAX_SUITS:
                continue

            card = make_card(rank, suit)

            if card in hand:
                continue

            hand.append(card)

            yield from _dfs(hand, target)

            hand.pop()