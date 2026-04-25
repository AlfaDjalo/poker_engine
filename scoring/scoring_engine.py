import poker_eval as _poker_eval
from scoring.score_result import ScoreResult
from cards.suit_iso import canonicalize_state

# from cards.card import Card
# print("Card 42 =", Card(42))
# print("Card 16 =", Card(16)) 
# print("Card 4  =", Card(4))

class CppScoringEngine:

    def evaluate(self, player_masks, board_mask, score_type, showdown_type):

        player_masks, board_mask = canonicalize_state(
            player_masks,
            board_mask
        )

        print("player_masks: ", player_masks)
        print("board_mask: ", board_mask)
        print("score_type: ", score_type)
        print("showdown_type: ", showdown_type)

        raw_scores = _poker_eval.evaluate_hands(
            player_masks,
            board_mask,
            score_type,
            showdown_type
        )

        print("raw_scores: ", raw_scores)

        return [ScoreResult(tuple(s)) for s in raw_scores]

    # backwards compatibility
    def evaluate_hands(self, *args, **kwargs):
        return self.evaluate(*args, **kwargs)