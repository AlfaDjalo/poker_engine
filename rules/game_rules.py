from poker_eval import ScoreType, ShowdownType

class GameRules:

    score_types = [ScoreType.HIGH]
    showdown_type = ShowdownType.HOLDEM          # single value, not a list

    def qualifies(self, score_type, score):
        return score is not None

    def best_score(self, score_type, scores):
        if score_type == ScoreType.LOW_27:
            return min(scores)
        return max(scores)