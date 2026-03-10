from dataclasses import dataclass
from typing import List, Optional


@dataclass
class GameDefinition:
    hole_cards: int
    board_cards_per_street: List[int]

    score_types: List
    low_qualifier: Optional[int] = None

    small_blind: int = 1
    big_blind: int = 2
    ante: int = 0