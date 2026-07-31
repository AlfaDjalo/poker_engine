# showdown/point_result.py

from dataclasses import dataclass
from typing import List


@dataclass
class PlayerPointResult:
    player_index: int
    rank: int
    best_hand_mask: int
    value: int
    category: str
    share: float
    best_hand_cards: List[int]
    hole_cards_used: List[int]
    board_cards_used: List[int]
    is_winner: bool


@dataclass
class PointResult:
    name: str
    showdown_type: str
    score_type: str
    node_mask: int
    results: list[PlayerPointResult]