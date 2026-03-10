from collections import defaultdict
from typing import Dict, List

from poker_eval import ScoreType

from .showdown_result import ShowdownResult
from rules.game_rules import GameRules

class ShowdownResolver:
    """
    Resolves poker showdowns.

    Supports:
    - side pots
    - multiple boards
    - multiple scoring types (Hi/Lo)
    - qualifiers
    - deterministic chip distribution
    """

    __slots__ = ("scoring_engine", "rules", "debug")

    def __init__(self, scoring_engine, rules, debug: bool = False):
        self.scoring_engine = scoring_engine
        self.rules = rules
        self.debug = debug

    # -----------------------------------------------------

    def resolve(self, game_state) -> ShowdownResult:

        side_pots = game_state.build_side_pots()

        # -----------------------------------------
        # collect active players
        # -----------------------------------------

        active = [
            i for i, p in enumerate(game_state.players)
            if not p.has_folded
        ]

        if not active:
            return ShowdownResult({}, [], {}, [])

        active_index = {p: i for i, p in enumerate(active)}

        player_masks = [
            game_state.players[i].hand_mask
            for i in active
        ]

        boards = self._extract_boards(game_state)

        showdown_type = self.rules.showdown_type        # single value

        # -----------------------------------------
        # evaluate scores
        # -----------------------------------------

        scores_by_type: Dict[ScoreType, List] = {}

        for score_type in self.rules.score_types:

            board_scores = []

            for board_mask in boards:

                # use the engine's public evaluate() method
                scores = self.scoring_engine.evaluate(
                    player_masks,
                    board_mask,
                    score_type,
                    showdown_type
                )

                board_scores.append(scores)

            scores_by_type[score_type] = board_scores

        payouts = defaultdict(int)

        winners_by_pot = []

        # -----------------------------------------
        # resolve each pot
        # -----------------------------------------

        for pot_amount, eligible in side_pots:

            contenders = [
                p for p in eligible
                if not game_state.players[p].has_folded
            ]

            if not contenders:
                continue

            pot_winners = self._resolve_pot(
                pot_amount,
                contenders,
                active_index,
                scores_by_type,
                boards
            )

            winners_by_pot.append(pot_winners)

            for player, amount in pot_winners.items():
                payouts[player] += amount

        # -----------------------------------------
        # apply payouts
        # -----------------------------------------

        for player, amount in payouts.items():
            game_state.players[player].stack += amount

        if self.debug:
            self._debug_output(
                game_state,
                payouts,
                scores_by_type,
                boards
            )

        return ShowdownResult(
            payouts=dict(payouts),
            winners_by_pot=winners_by_pot,
            scores=scores_by_type,
            boards=boards
        )

    # -----------------------------------------------------

    def _resolve_pot(
        self,
        pot_amount,
        contenders,
        active_index,
        scores_by_type,
        boards
    ):

        payouts = defaultdict(int)

        num_types = len(self.rules.score_types)
        num_boards = len(boards)

        split_unit = pot_amount // (num_types * num_boards)
        remainder = pot_amount % (num_types * num_boards)

        for score_type in self.rules.score_types:

            board_scores = scores_by_type[score_type]

            for scores in board_scores:

                contender_scores = []

                for p in contenders:
                    s = scores[active_index[p]]

                    if self.rules.qualifies(score_type, s):
                        contender_scores.append((p, s))

                if not contender_scores:
                    continue

                best_score = self.rules.best_score(
                    score_type,
                    [s for _, s in contender_scores]
                )

                winners = [
                    p for p, s in contender_scores
                    if s == best_score
                ]

                share = split_unit // len(winners)
                extra = split_unit % len(winners)

                for w in winners:
                    payouts[w] += share

                for i in range(extra):
                    payouts[winners[i]] += 1

        for i in range(remainder):
            payouts[contenders[i % len(contenders)]] += 1

        return payouts

    # -----------------------------------------------------

    def _extract_boards(self, game_state):

        if hasattr(game_state, "board_masks"):
            return game_state.board_masks

        return [game_state.board_mask]

    # -----------------------------------------------------

    def _debug_output(
        self,
        game_state,
        payouts,
        scores,
        boards
    ):

        print("=== SHOWDOWN ===")

        print("Boards:")

        for b in boards:
            print(f"  {b:b}")

        print("\nScores:")

        for score_type, board_scores in scores.items():

            print(score_type)

            for b_index, s in enumerate(board_scores):

                print(f" Board {b_index}")

                for i, score in enumerate(s):
                    print(f"  Player {i}: {score}")

        print("\nPayouts")

        for p, amt in payouts.items():
            print(f"Player {p} +{amt}")