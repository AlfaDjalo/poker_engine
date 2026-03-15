from typing import List, Tuple

from poker_eval import ScoreType


class PointDefinition:
    """
    Defines a scoring point in a poker game.

    A point corresponds to one or more board configurations.
    Each configuration is defined by a set of node indices.
    """

    __slots__ = (
        "name",
        "score_type",
        "node_sets",
        "board_masks"
    )

    def __init__(
            self,
            name: str,
            score_type: ScoreType,
            node_sets: List[Tuple[int, ...]]
    ):
        self.name = name
        self.score_type = score_type
        self.node_sets = node_sets
    
        board_masks: List[int] = []

    # -----------------------------------------------------

    def generate_board_masks(self, node_cards):
        """
        Converts node_sets into bitmask boards using node_cards.
        """

        boards = []

        for node_set in self.node_sets:

            mask = 0

            for node in node_set:

                card = node_cards[node]

                if card is None:
                    continue

                mask |= 1 << card

            boards.append(mask)

        self.board_masks = boards

        return boards