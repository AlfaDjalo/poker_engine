from dataclasses import dataclass
from typing import Dict, List
from poker_eval import ScoreType

@dataclass
class ShowdownResult:
    """
    Result of a showdown resolution.
    Useful for debugging, UI, logging, and RL training.
    """

    payouts: Dict[int, int]

    winners_by_pot: List[List[int]]

    scores: Dict[ScoreType, List]

    boards: List[int]
