import poker_engine.poker_eval as _poker_eval
from poker_engine.scoring.score_result import ScoreResult
from poker_engine.cards.suit_iso import canonicalize_state

# from cards.card import Card
# print("Card 42 =", Card(42))
# print("Card 16 =", Card(16)) 
# print("Card 4  =", Card(4))

class CppScoringEngine:

    def __init__(self, debug: bool = False):
        self.debug = debug

    def evaluate(self, player_masks, board_mask, score_type, showdown_type):

        # player_masks, board_mask = canonicalize_state(
        #     player_masks,
        #     board_mask
        # )

        if self.debug:
            print("player_masks: ", player_masks)
            print("board_mask: ", board_mask)
            print("score_type: ", score_type)
            print("showdown_type: ", showdown_type)

        # print("player_masks types:", [type(x) for x in player_masks])
        # print("board_mask type:", type(board_mask))

        raw_scores = _poker_eval.evaluate_hands(
            player_masks,
            board_mask,
            _poker_eval.ScoreType(score_type.value),
            _poker_eval.ShowdownType(showdown_type.value)
        )

        if self.debug:
            print("raw_scores: ", raw_scores)

        return [ScoreResult((s[0],), best_hand_mask=s[1] if len(s) > 1 else 0) for s in raw_scores]

    # backwards compatibility
    def evaluate_hands(self, *args, **kwargs):
        return self.evaluate(*args, **kwargs)