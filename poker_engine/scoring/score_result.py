from dataclasses import dataclass
from typing import Tuple

@dataclass(frozen=True)
class ScoreResult:
    """
    Represents the evaluated strength of a hand.
    
    The score is a tuple of integers ordered from most significant
    to least significant for lexicographic comparison.
    
    Higher tuples values represent stronger hands.
    """

    score: Tuple[int, ...]
    best_hand_mask: int = 0 # Not sure about this

    def __lt__(self, other: "ScoreResult") -> bool:
        return self.score < other.score
    
    def __gt__(self, other: "ScoreResult") -> bool:
        return self.score > other.score
    
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ScoreResult):
            return False
        return self.score == other.score

    def __repr__(self):
        return f"ScoreResult{self.score}"