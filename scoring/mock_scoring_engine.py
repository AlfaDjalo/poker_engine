from scoring.score_result import ScoreResult

class MockScoringEngine:
    """Mock scoring engine for testing without C++ evaluator."""

    def evaluate(self, player_masks, board_mask, score_type):
        # Return dummy scores for testing
        num_players = len(player_masks)
        return [ScoreResult((1, 2, 3, 4, 5)) for _ in range(num_players)]