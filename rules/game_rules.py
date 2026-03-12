from poker_eval import ScoreType, ShowdownType

class GameRules:

    def __init__(self, score_types, showdown_type):
        self.score_types = score_types
        self.showdown_type = showdown_type

    def qualifies(self, score_type, score):
        return score is not None

    def best_score(self, score_type, scores):
        if score_type == ScoreType.LOW_27:
            return min(scores)
        return max(scores)