from poker_eval import evaluate_hands
from scoring.score_result import ScoreResult
from cards.suit_iso import canonicalize_state

class CppScoringEngine:

    def evaluate(self, player_masks, board_mask, score_type, showdown_type):

        player_masks, board_mask = canonicalize_state(
            player_masks,
            board_mask
        )

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