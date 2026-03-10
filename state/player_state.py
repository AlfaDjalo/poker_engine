from dataclasses import dataclass
from cards.mask import CardMask


@dataclass
class PlayerState:
    stack: int
    hand_mask: CardMask = 0

    current_bet: int = 0
    total_contribution: int = 0

    has_folded: bool = False
    is_all_in: bool = False