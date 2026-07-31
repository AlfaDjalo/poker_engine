# poker_engine/state/hand_snapshot.py

from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class PlayerSnapshot:
    stack: int
    hand_mask: int
    current_bet: int
    total_contribution: int
    has_folded: bool
    is_all_in: bool

@dataclass
class HandSnapshot:
    game_name: str
    street_index: int
    pot: int
    dealer_position: int
    current_player: int
    bet_to_call: int
    min_raise: int
    players: List[PlayerSnapshot]
    node_cards: List[Optional[int]]
    discard_pile: List[int] = field(default_factory=list)
    raises_this_street: int = 0
    last_aggressor: Optional[int] = None