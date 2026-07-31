from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .point_result import PointResult

# from poker_eval import ScoreType

@dataclass
class ShowdownResult:
    """
    Result of a showdown resolution.
    Useful for debugging, UI, logging, and RL training.
    """
    payouts: Dict[int, int]
    winners_by_pot: List[List[int]]
    # scores: Dict[ScoreType, List]
    # boards: List[int]
    payout_type: str = "points"
    points: Optional[List[PointResult]] = None
    point_tallies: Optional[Dict[int, float]] = None
    scoop_flags: Optional[List[List[bool]]] = None