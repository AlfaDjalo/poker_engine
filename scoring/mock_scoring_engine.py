"""
scoring/mock_scoring_engine.py

Stub evaluator for use in tests that don't require the C++ poker_eval extension.
Returns deterministic dummy scores so showdown resolution logic can be exercised
without building the native extension.

Usage:
    engine = MockScoringEngine()
    # All players receive score (1, player_index) so player 0 always wins ties.
    # Pass ranked=True to give each player a unique score proportional to
    # their position in player_masks, making winner prediction trivial in tests.
"""

from scoring.score_result import ScoreResult


class MockScoringEngine:

    def evaluate(
        self,
        player_masks,
        board_mask,
        score_type,
        showdown_type=None,     # FIX: was missing; ShowdownResolver passes 4 args
    ):
        """
        Return a dummy ScoreResult for every player.

        The score is (1_500_000 + i,) so that:
        - Every player has a valid "One Pair" tier score (> 0, non-zero).
        - Player at index 0 in player_masks has the lowest score; the last
          player has the highest — making winners predictable in unit tests.
        - The gap of 1 per player means no ties unless the same player
          appears twice.
        """
        return [
            ScoreResult((1_500_000 + i,), best_hand_mask=mask)
            for i, mask in enumerate(player_masks)
        ]

    # backwards compatibility alias
    def evaluate_hands(self, *args, **kwargs):
        return self.evaluate(*args, **kwargs)