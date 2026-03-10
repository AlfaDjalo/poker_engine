from poker_eval import evaluate_hands
from scoring.score_result import ScoreResult

class CppScoringEngine:

    def evaluate(self, player_masks, board_mask, score_type, showdown_type):

        raw_scores = evaluate_hands(
            player_masks,
            board_mask,
            score_type,
            showdown_type
        )

        return [ScoreResult(tuple(s)) for s in raw_scores]

    # backwards compatibility
    def evaluate_hands(self, *args, **kwargs):
        return self.evaluate(*args, **kwargs)