from typing import List, Tuple

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
        "points"
    )

    def __init__(
            self,
            score_types: List[ScoreType],
            showdown_type: ShowdownType,
            points: List[PointDefinition]
    ):
        
        self.score_types = score_types
        self.showdown_type = showdown_type
        self.points = points

    def qualifies(self, score_type, score):
        return score is not None

    def best_score(self, score_type, scores):
        if score_type == ScoreType.LOW_27:
            return min(scores)
        return max(scores)
    
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