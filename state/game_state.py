from typing import List
from cards.deck import FULL_DECK_MASK
from .player_state import PlayerState
from actions.action_type import ActionType


class GameState:

    __slots__ = (
        "players",
        "deck_mask",
        "board_mask",
        "pot",
        "dealer_position",
        "current_player",
        "street_index",
        "bet_to_call",
        "min_raise",
        "players_acted",
        "last_aggressor",
        "raises_this_street",
    )

    def __init__(self, players: List[PlayerState]):

        self.players = players

        self.deck_mask = FULL_DECK_MASK
        self.board_mask = 0

        self.pot = 0

        self.dealer_position = 0
        self.current_player = 0

        self.street_index = 0

        self.bet_to_call = 0
        self.min_raise = 0

        self.players_acted = 0
        self.last_aggressor = None
        self.raises_this_street = 0

    # -----------------------------------------------------
    # Card utilities
    # -----------------------------------------------------

    def draw_card(self):

        available = self.deck_mask
        lsb = available & -available
        card = lsb.bit_length() - 1

        self.deck_mask ^= lsb

        return card

    # -----------------------------------------------------
    # Turn management
    # -----------------------------------------------------

    def advance_turn(self):

        n = len(self.players)

        for i in range(1, n + 1):

            idx = (self.current_player + i) % n
            p = self.players[idx]

            if not p.has_folded and not p.is_all_in:
                self.current_player = idx
                return

    def active_players(self):

        return [
            i for i, p in enumerate(self.players)
            if not p.has_folded and not p.is_all_in
        ]

    def remaining_players(self):

        return [
            i for i, p in enumerate(self.players)
            if not p.has_folded
        ]

    # -----------------------------------------------------
    # Betting logic
    # -----------------------------------------------------

    def apply_action(self, action):

        player = self.players[self.current_player]

        if action.type == ActionType.FOLD:

            player.has_folded = True
            self.players_acted += 1

        elif action.type == ActionType.CHECK:

            self.players_acted += 1

        elif action.type == ActionType.CALL:

            to_call = self.bet_to_call - player.current_bet
            amount = min(to_call, player.stack)

            player.stack -= amount
            player.current_bet += amount
            player.total_contribution += amount

            self.pot += amount

            if player.stack == 0:
                player.is_all_in = True

            self.players_acted += 1

        elif action.type in (ActionType.BET, ActionType.RAISE):

            to_call = self.bet_to_call - player.current_bet
            total = to_call + action.amount

            player.stack -= total
            player.current_bet += total
            player.total_contribution += total

            self.pot += total

            if player.stack == 0:
                player.is_all_in = True

            self.min_raise = action.amount
            self.bet_to_call = player.current_bet

            self.players_acted = 1
            self.last_aggressor = self.current_player
            self.raises_this_street += 1

    # -----------------------------------------------------
    # Betting round completion
    # -----------------------------------------------------

    def betting_round_complete(self):

        remaining = self.remaining_players()

        if len(remaining) <= 1:
            return True

        active = self.active_players()

        if self.players_acted >= len(active):
            return True

        return False

    def reset_betting_round(self):

        for p in self.players:
            p.current_bet = 0

        self.bet_to_call = 0
        self.min_raise = 0

        self.players_acted = 0
        self.last_aggressor = None
        self.raises_this_street = 0

    # -----------------------------------------------------
    # Pot handling
    # -----------------------------------------------------

    def build_side_pots(self):

        contributions = [
            (i, p.total_contribution)
            for i, p in enumerate(self.players)
            if p.total_contribution > 0
        ]

        if not contributions:
            return []

        contributions.sort(key=lambda x: x[1])

        side_pots = []
        prev = 0

        remaining_players = set(i for i, _ in contributions)

        for i, amount in contributions:

            if amount > prev:

                layer = amount - prev
                pot_amount = layer * len(remaining_players)

                side_pots.append((pot_amount, remaining_players.copy()))

                prev = amount

            remaining_players.remove(i)

        return side_pots