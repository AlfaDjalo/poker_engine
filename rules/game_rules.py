from typing import List, Optional

from .point_definition import PointDefinition
from poker_eval import ScoreType, ShowdownType


class GameRules:
    """
    Defines the scoring rules for a poker game.

    Handles:
    - score types (Hi / Lo etc.)
    - showdown type
    - point definitions (board layouts)
    - score comparison logic
    - qualification logic
    """
    __slots__ = (
        "score_types",
        "showdown_type",
        "points",
        "payout_type",
        "low_qualifier",
        "no_qualify_action",
    )

    def __init__(
            self,
            score_types: List[ScoreType],
            showdown_type: ShowdownType,
            points: List[PointDefinition],
            payout_type: str = "points",
            low_qualifier: Optional[int] = None,
            no_qualify_action: str = "scoop",       # "scoop" | "eliminate"
    ):
        
        self.score_types = score_types
        self.showdown_type = showdown_type
        self.points = points
        self.payout_type = payout_type
        self.low_qualifier = low_qualifier
        self.no_qualify_action = no_qualify_action

    def qualifies(self, score_type, score):
        """
        Returns True if the score qualifies for this point type.
        """
        if score is None:
            return False
        if score.score[0] == 0:
            return False
        if self.is_low_type(score_type):
            if self.low_qualifier is not None:
                # score.score[0] is the encoded low hand; extract highest rank (lowest 4 bits)
                highest_rank = (score.score[0] >> 16) & 0xF
                # highest_rank = score.score[0] & 0xF
                print("score.score: ", bin(score.score[0]))
                print("highest_rank: ", highest_rank)
                return 0 < highest_rank <= self.low_qualifier
        return True

    def best_score(self, score_type, scores):
        if self.is_low_type(score_type):
            return min(scores)
        return max(scores)
    
    def is_low_type(self, score_type):
        return score_type in (ScoreType.LOW_A5, ScoreType.LOW_27)

    def generate_boards(self, node_cards):
        """
        Generate board masks for every point.
        """

        boards = []

        for point in self.points:

            point_boards = point.generate_board_masks(node_cards)

            boards.append({
                "name": point.name,
                "score_type": point.score_type,
                "boards": point_boards
            })

        return boards