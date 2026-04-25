from collections import defaultdict
from typing import Dict, List
from cards.mask import mask_to_card_ids

from poker_eval import ScoreType

from .showdown_result import ShowdownResult
from .point_result import PlayerPointResult, PointResult

class ShowdownResolver:
    """
    Resolves poker showdowns.

    Supports:
    - side pots
    - multiple boards
    - CAP node boards
    - multiple scoring types (Hi/Lo)
    - qualifiers
    - two payout types:
        "split_pot":    each component wins an independent share of the pot
        "points":       player with most points wins the entire pot (chop if tied)
    """

    __slots__ = ("scoring_engine", "rules", "debug", "_last_point_tallies")

    def __init__(self, scoring_engine, rules, debug: bool = True):

        self.scoring_engine = scoring_engine
        self.rules = rules
        self.debug = debug
        self._last_point_tallies = None


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
        # evaluate scores
        # -----------------------------------------

        scores_by_point = self._evaluate_all_points(player_masks, game_state)

        structured_points = self._build_structured_points(
            scores_by_point,
            active,
            active_index,
            game_state
        )

        payouts = defaultdict(int)
        winners_by_pot = []

        # -----------------------------------------
        # resolve each pot
        # -----------------------------------------

        self._last_point_tallies = None

        scoop_flags_combined = []

        for pot_amount, eligible in side_pots:

            contenders = [
                p for p in eligible
                if not game_state.players[p].has_folded
            ]

            if not contenders:
                continue

            if self.rules.payout_type == "split_pot":
                pot_winners, scoop_flags = self._resolve_split_pot(
                    pot_amount, contenders, active_index, scores_by_point
                )
                if scoop_flags:
                    scoop_flags_combined.extend(scoop_flags)
            else:
                pot_winners = self._resolve_points_game(
                    pot_amount, contenders, active_index, scores_by_point
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
            self._debug_output(game_state, payouts, scores_by_point)

        return ShowdownResult(
            payouts=dict(payouts),
            winners_by_pot=winners_by_pot,
            payout_type=self.rules.payout_type,
            point_tallies=self._last_point_tallies,
            scoop_flags=scoop_flags_combined if scoop_flags_combined else None,
            points=structured_points
        )

    # -----------------------------------------------------

    def _evaluate_all_points(self, player_masks, game_state):
        """
        Evaluate scores for every point and every board within each point.
        Returns list of:
            { name, score_type, boards: [mask, ...], scores: [[ScoreResult, ...], ...]}
        """
        points = self._generate_points(game_state)
        scores_by_point = []

        for point_def, point in zip(self.rules.points, points):
            showdown_type = (
                point_def.showdown_type_override
                if point_def.showdown_type_override is not None
                else self.rules.showdown_type
            )
            
            
            board_scores = []
            for board_mask in point["boards"]:
                scores = self.scoring_engine.evaluate(
                    player_masks,
                    board_mask,
                    point["score_type"],
                    showdown_type
                )
                board_scores.append(scores)

            scores_by_point.append({
                "name": point["name"],
                "score_type": point["score_type"],
                "showdown_type": showdown_type,
                "boards": point["boards"],
                "scores": board_scores,
            })

        return scores_by_point

    # --------------------------------------------------
    # Split pot resolution
    # --------------------------------------------------

    def _resolve_split_pot(
            self, pot_amount, contenders, active_index, scores_by_point
    ):
        """
        Each component (point x board) independently wins an equal share
        of the pot.

        num_components = total number of (point, board) pairs.
        Each component is worth pot_amount // num_components.
        """
        payouts = defaultdict(int)

        # Build a lookup of point results by name for scoop resolution
        point_results = {
            p["name"]: p for p in scores_by_point
        }
        point_defs = {
            pd.name: pd for pd in self.rules.points
        }

        # Count total independent components
        num_components = sum(
            len(p["scores"]) for p in scores_by_point
        )

        if num_components == 0:
            return payouts
        
        # Integer division - track remainder for correct chip distribution
        base_share = pot_amount // num_components
        remainder = pot_amount % num_components
        component_index = 0

        scoop_flags = [[False] * len(p["scores"]) for p in scores_by_point]

        for point_idx, point in enumerate(scores_by_point):
            score_type = point["score_type"]
            point_def = point_defs.get(point["name"])

            for board_idx, board_scores in enumerate(point["scores"]):

                # Each component gets base_share, plus 1 chip from remainder
                component_pot = base_share + (1 if component_index < remainder else 0)
                component_index += 1

                winners  = self._winners_for_board(
                    board_scores, contenders, active_index, score_type
                )

                if not winners:
                    winners = self._handle_no_qualify(
                        point_def, board_idx, contenders,
                        active_index, point_results, score_type
                    )
                    if winners:
                        scoop_flags[point_idx][board_idx] = True

                if winners:
                    self._distribute(component_pot, winners, payouts)

        return dict(payouts), scoop_flags

    # --------------------------------------------------
    # Points game resolution
    # --------------------------------------------------

    def _resolve_points_game(
        self, pot_amount, contenders, active_index, scores_by_point
    ):
        """
        Tally one point per (point x board) component won.
        Player(s) with the most points win the entire pot.
        Ties in points -> chop.
        """
        # Tally points per contender
        point_tally = defaultdict(int)

        point_results = {p["name"]: p for p in scores_by_point}
        point_defs = {pd.name: pd for pd in self.rules.points}

        for point in scores_by_point:
            score_type = point["score_type"]
            point_def = point_defs.get(point["name"])

            for board_idx, board_scores in enumerate(point["scores"]):

                winners = self._winners_for_board(
                    board_scores, contenders, active_index, score_type
                )

                if not winners:
                    winners = self._handle_no_qualify(
                        point_def, board_idx, contenders,
                        active_index, point_results, score_type
                    )

                if not winners:
                    continue

                # In a points game, a shared board distributes
                # the points amongst the winners
                share = 1 / len(winners)
                for w in winners:
                    point_tally[w] += share

        self._last_point_tallies = dict(point_tally)

        if not point_tally:
            return {}
        
        max_points = max(point_tally.values())

        # Only include players who actually won at least one component (> 0 points)
        pot_winners = [
            p for p in contenders
            if point_tally.get(p, 0.0) >= max_points - 1e-9
        ]

        payouts = defaultdict(int)
        self._distribute(pot_amount, pot_winners, payouts)
        return dict(payouts)

    def _handle_no_qualify(
            self, point_def, board_idx, contenders,
            active_index, point_results, score_type
    ):
        """
        Called when no player qualifies for a low point.
        Returns the list of winnres to award this component to,
        based on no_qualify_action.
        """
        if not self.rules.is_low_type(score_type):
            return []
        
        action = self.rules.no_qualify_action

        if action == "eliminate":
            # Component is void - no-one gets it
            return []
        
        elif action == "scoop":
            # Award to the winner of the paired high point
            if point_def and point_def.scoop_from:
                paired = point_results.get(point_def.scoop_from)
                if paired and board_idx < len(paired["scores"]):
                    return self._winners_for_board(
                        paired["scores"][board_idx],
                        contenders,
                        active_index,
                        paired["score_type"]
                    )
                
            # No paired point defined - fall back to eliminate
            return []
        
        return []

    # --------------------------------------------------
    # Shared helpers
    # --------------------------------------------------

    def _winners_for_board(self, board_scores, contenders, active_index, score_type):
        """
        Return the list of contender players who have the best score
        on a given board. Returns [] if no contender qualifies.
        """
        contender_scores = []

        for p in contenders:
            s = board_scores[active_index[p]]
            if self.rules.qualifies(score_type, s):
                contender_scores.append((p, s))

        if not contender_scores:
            return []
        
        best = self.rules.best_score(
            score_type, [s for _, s in contender_scores]
        )

        return [p for p, s in contender_scores if s == best]
    

    def _distribute(self, amount, winners, payouts):
        """
        Distribute amount evenly among winners, remainder to first winner(s).
        """
        if not winners:
            return
        share = amount // len(winners)
        remainder = amount % len(winners)
        for w in winners:
            payouts[w] += share
        for i in range(remainder):
            payouts[winners[i]] += 1


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
                    if card is not None:
                        mask |= 1 << card

                board_masks.append(mask)

            points.append({
                "name": point.name,
                "score_type": point.score_type,
                "boards": board_masks
            })

        return points

    # -----------------------------------------------------

    def _debug_output(self, game_state, payouts, scores_by_point):
        print("=== SHOWDOWN ===")
        print(f"Payout type: {self.rules.payout_type}")

        active_players = [
            i for i, p in enumerate(game_state.players)
            if not p.has_folded
        ]

        for point in scores_by_point:
            score_type_name = (
                point["score_type"].name
                if hasattr(point["score_type"], "name")
                else str(point["score_type"])
            )
            print(f"\nPoint: {point['name']} ({score_type_name})")

            for board_idx, board_scores in enumerate(point["scores"]):
                board_mask = point["boards"][board_idx] if board_idx < len(point["boards"]) else None
                print(f" Board {board_idx} mask={board_mask}")
                for player_idx, score in zip(active_players, board_scores):
                    decoded = self._decode_score(score, point["score_type"])
                    print(f"  Player {player_idx}: {decoded}")

        print("\nPayouts:")
        for p, amt in payouts.items():
            print(f"  Player {p} +{amt}")

    def _format_score(self, score):
        if score is None:
            return "None"
        if hasattr(score, "score"):
            return f"{getattr(score, 'score')} ({score})"
        return str(score)

    def _decode_score(self, score_result, score_type):
        if score_result is None:
            return "None"
        v = score_result.score[0]
        if v == 0:
            return "No hand"

        from poker_eval import ScoreType as ST

        if score_type == ST.HIGH:
            if v >= 7_000_000: cat = "Straight Flush"
            elif v >= 6_000_000: cat = "Quads"
            elif v >= 5_000_000: cat = "Full House"
            elif v >= 4_000_000: cat = "Flush"
            elif v >= 3_000_000: cat = "Straight"
            elif v >= 2_000_000: cat = "Three of a Kind"
            elif v >= 1_000_000: cat = "Two Pair"
            elif v >= 500_000: cat = "One Pair"
            else: cat = "High Card"
            return f"{cat} [{v}]"

        if self.rules.is_low_type(score_type):
            # Decode 4-bit nibble packing: 5 ranks, lowest first (MSB)
            RANK_NAMES = {1:"A", 2:"2", 3:"3", 4:"4", 5:"5",
                        6:"6", 7:"7", 8:"8", 9:"9", 10:"T",
                        11:"J", 12:"Q", 13:"K"}
            ranks = []
            tmp = v
            for _ in range(5):
                ranks.append(tmp & 0xF)
                tmp >>= 4
            # ranks.reverse()
            hand_str = "-".join(RANK_NAMES.get(r, str(r)) for r in ranks)
            return f"Low {hand_str} [{v}]"
        
        return f"Score [{v}]"

    def _build_structured_points(
        self,
        scores_by_point,
        active,
        active_index,
        game_state
    ):
        """
        Convert raw score output into DB-ready structured points.
        """

        structured = []

        for point in scores_by_point:

            name = point["name"]
            score_type = point["score_type"]
            showdown_type = point["showdown_type"]

            for board_idx, board_scores in enumerate(point["scores"]):
                
                node_mask = point["boards"][board_idx]

                winners = self._winners_for_board(
                    board_scores,
                    active,
                    active_index,
                    score_type
                )

                # rank players
                scored_players = []

                for p in active:
                    score = board_scores[active_index[p]]

                    if score is None or not self.rules.qualifies(score_type, score):
                        continue

                    scored_players.append((p, score))

                if not scored_players:
                    continue

                # -------------------------
                # Sort players
                # ------------------------- 
                reverse = not self.rules.is_low_type(score_type)
                scored_players.sort(
                    key=lambda x: x[1].score[0],
                    reverse=reverse
                )

                results = []
                current_rank = 1

                for i, (p, score) in enumerate(scored_players):

                    if i > 0 and score.score[0] != scored_players[i - 1][1].score[0]:
                        current_rank = i + 1

                    best_mask = getattr(score, "best_hand_mask", 0)

                    best_cards = self._mask_to_cards(best_mask)
                    board_cards = self._mask_to_cards(node_mask)
                    hole_cards = self._mask_to_cards(
                        game_state.players[p].hand_mask
                    )

                    board_used = [c for c in best_cards if c in board_cards]
                    hole_used = [c for c in best_cards if c in hole_cards]

                    results.append(
                        PlayerPointResult(
                            player_index=p,
                            rank=current_rank,
                            best_hand_mask=best_mask,
                            value=score.score[0],
                            category=self._category(score, score_type),
                            share=0.0,
                            best_hand_cards=best_cards,
                            hole_cards_used=hole_used,
                            board_cards_used=board_used,
                            is_winner=(p in winners),
                        )
                    )

                # -------------------------
                # Assign point shares
                # -------------------------
                if winners:
                    share = 1.0 / len(winners)
                    for r in results:
                        if r.player_index in winners:
                            r.share = share

                structured.append(
                    PointResult(
                        name=name,
                        showdown_type=(
                            showdown_type.name
                            if hasattr(showdown_type, "name")
                            else str(showdown_type)
                        ),
                        score_type=score_type.name,
                        node_mask=node_mask,
                        results=results
                    )
                )

        return structured
        

    def _category(self, score_result, score_type):

        if score_result is None:
            return "NONE"

        v = score_result.score[0]

        if score_type == ScoreType.HIGH:
            if v >= 8_000_000: return "STRAIGHT_FLUSH"
            if v >= 7_000_000: return "QUADS"
            if v >= 6_000_000: return "FULL_HOUSE"
            if v >= 5_000_000: return "FLUSH"
            if v >= 4_000_000: return "STRAIGHT"
            if v >= 3_000_000: return "TRIPS"
            if v >= 2_000_000: return "TWO_PAIR"
            if v >= 1_000_000: return "PAIR"
            return "HIGH_CARD"
        
        if self.rules.is_low_type(score_type):
            return "LOW"
        
        return "OTHER"

    def _mask_to_cards(self, mask):
        cards = []
        while mask:
            lsb = mask & -mask
            cid = lsb.bit_length() - 1
            cards.append(cid)
            mask ^= lsb
        
        return cards

def decode_hand_mask(mask, node_mask, player_mask):
    cards = mask_to_card_ids(mask)
    board_cards = mask_to_card_ids(mask & node_mask)
    hole_cards = mask_to_card_ids(mask & player_mask)

    return cards, hole_cards, board_cards

