from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class GameDefinition:
    hole_cards: int
    board_cards_per_street: List[int]
    node_count: int
    street_nodes: List[List[int]]
    
    score_types: List
    low_qualifier: Optional[int] = None

    betting_type: str = "holdem"

    small_blind: int = 1
    big_blind: int = 2
    ante: int = 0

    layout_name: Optional[str] = None       # e.g. "double_board"
    game_name: Optional[str] = None         # e.g. "double_board_plo_bomb_pot"