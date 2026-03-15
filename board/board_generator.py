from typing import Iterable, List, Optional

from constraints.engine import ConstraintEngine
from constraints.types import NodeMask
from cards.deck import FULL_DECK_MASK
from .canonical_board_generator import generate_canonical_boards

# from cards.suit_iso import unique_canonical_masks

from .board_enumerator import choose_k


class BoardGenerator:
    """
    Generates valid board masks subject to constraints.
    
    Supports:
    - dead cards
    - multi-street boards
    - constraint filtering
    """

    __slots__ = (
        "board_cards_per_street",
        "constraint_engine",
    )

    def __init__(
            self,
            board_cards_per_street: List[int],
            constraint_engine: Optional[ConstraintEngine] = None,
    ):
        self.board_cards_per_street = board_cards_per_street
        self.constraint_engine = constraint_engine or ConstraintEngine()

    # -----------------------------------------------------

    def generate_boards(
            self,
            dead_mask: NodeMask = 0
    ) -> Iterable[NodeMask]:
        """
        Generate full board masks.
        """

        available = FULL_DECK_MASK & ~dead_mask

        total_cards = sum(self.board_cards_per_street)

        boards = generate_canonical_boards(total_cards)

        for board in boards:
        # for board in choose_k(available, total_cards):

            if self.constraint_engine.validate(board):
                yield board

        # boards = choose_k(available, total_cards)

        # for board in unique_canonical_masks(boards):

        #     if self.constraint_engine.validate(board):
        #         yield board

    # -----------------------------------------------------
    
    def generate_by_street(
            self,
            dead_mask: NodeMask = 0
    ) -> Iterable[List[NodeMask]]:
        """
        Generate boards street-by-street.
        
        Yields list of board masks:
        [flop_mask, turn_mask, river_mask]
        """
        available = FULL_DECK_MASK & ~dead_mask

        streets = self.board_cards_per_street

        def dfs(street_index, used_mask, boards):

            if street_index == len(streets):

                full_board = 0
                for b in boards:
                    full_board |= b

                if self.constraint_engine.validate(full_board):
                    yield boards.copy()

                return
            
            k = streets[street_index]

            remaining = available & ~used_mask

            for combo in choose_k(remaining, k):

                boards.append(combo)

                yield from dfs(
                    street_index + 1,
                    used_mask | combo,
                    boards
                )

                boards.pop()

            yield from dfs(0, 0, [])