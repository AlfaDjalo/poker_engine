from collections import defaultdict
from typing import Dict, List

from poker_eval import ScoreType

from .showdown_result import ShowdownResult


class ShowdownResolver:
    """
    Resolves poker showdowns.

    Supports:
    - side pots
    - multiple boards
    - CAP node boards
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

        # hand_ranks = {}
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

        # -----------------------------------------
        # generate board masks per point
        # -----------------------------------------

        points = self._generate_points(game_state)

        # -----------------------------------------
        # evaluate scores
        # -----------------------------------------

        scores_by_point = []

        for point in points:

            board_scores = []

            for board_mask in point["boards"]:

                scores = self.scoring_engine.evaluate(
                    player_masks,
                    board_mask,
                    point["score_type"],
                    self.rules.showdown_type
                )

                board_scores.append(scores)

            scores_by_point.append({
                "score_type": point["score_type"],
                "boards": point["boards"],
                "scores": board_scores
            })

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
                scores_by_point
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
                scores_by_point
            )

        return ShowdownResult(
            payouts=dict(payouts),
            winners_by_pot=winners_by_pot,
            scores=scores_by_point,
            boards=[p["boards"] for p in points],
            # hand_ranks=hand_ranks
        )

    # -----------------------------------------------------

    def _resolve_pot(
        self,
        pot_amount,
        contenders,
        active_index,
        scores_by_point
    ):

        payouts = defaultdict(int)

        num_points = sum(len(p["boards"]) for p in scores_by_point)

        split_unit = pot_amount // num_points
        remainder = pot_amount % num_points

        for point in scores_by_point:

            score_type = point["score_type"]

            for scores in point["scores"]:

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
        

    def _generate_points(self, game_state):
        """
        Converts rule point definitions into concrete board masks.
        """

        node_cards = game_state.node_cards

        points = []

        for point in self.rules.points:

            board_masks = []

            for node_set in point.node_sets:

                mask = 0

                for n in node_set:
                    card = node_cards[n]
                    mask |= 1 << card

                board_masks.append(mask)

            points.append({
                "name": point.name,
                "score_type": point.score_type,
                "boards": board_masks
            })

        return points

    # -----------------------------------------------------

    def _debug_output(
        self,
        game_state,
        payouts,
        scores_by_point
    ):

        print("=== SHOWDOWN ===")

        # print(f"\nPoint: {p['score_type']}")

        # for i, board in enumerate(p["boards"]):
            # print(f" Board {i}: {board:b}")

        print("\nPayouts")

        for p, amt in payouts.items():
            print(f"Player {p} +{amt}")
