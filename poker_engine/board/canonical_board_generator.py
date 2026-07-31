from typing import Iterable, List

from cards.mask import card_to_mask

RANKS = list(range(13))
SUITS = list(range(4))

def make_card(rank: int, suit: int) -> int:
    return suit * 13 + rank


def generate_canonical_boards(num_cards: int) -> Iterable[int]:
    """
    Generate canonical boards of num_cards cards.
    
    Uses canonical suit ordering to eliminate
    suit-isomorphic duplicates.
    """

    board: List[int] = []

    yield from _dfs(board, 0, num_cards)

    
def _dfs(board: List[int], next_suit: int, target: int):

    if len(board) == target:

        mask = 0
        for card in board:
            mask |= card_to_mask(card)

        yield mask
        return
    
    used_suits = {c // 13 for c in board}

    max_suit = max(used_suits) if used_suits else -1

    for rank in RANKS:

        for suit in range(max_suit + 2):
            if suit >= 4:
                continue

            # Prevent duplicate cards
            card = make_card(rank, suit)

            if card in board:
                continue

            board.append(card)

            yield from _dfs(board, next_suit, target)

            board.pop()