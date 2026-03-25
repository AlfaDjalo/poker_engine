from typing import Iterable, List
from cards.deck import FULL_DECK_MASK
from cards.mask import CardMask
from .player_state import PlayerState
from actions.action_type import ActionType


class GameState:

    __slots__ = (
        "players",
        "node_cards",
        "pot",
        "dealer_position",
        "current_player",
        "street_index",
        "bet_to_call",
        "min_raise",
        "players_acted",
        "last_aggressor",
        "raises_this_street",
        "last_to_act",
    )

    def __init__(self, players: List[PlayerState]):

        self.players = players

        # CAP board representation
        # index = node index
        # value = card index or None
        self.node_cards: List[int | None] = []

        self.pot = 0

        self.dealer_position = 0
        self.current_player = 0

        self.street_index = 0

        self.bet_to_call = 0
        self.min_raise = 0

        self.players_acted = 0
        self.last_aggressor = None
        self.last_to_act = None
        self.raises_this_street = 0

    # -----------------------------------------------------
    # Board helpers
    # -----------------------------------------------------

    def node_mask(self, nodes: Iterable[int]) -> CardMask:
        """
        Convert node indices into a CardMask.
        """ 

        mask = 0

        for n in nodes:

            card = self.node_cards[n]

            if card is not None:
                mask |= 1 << card

        return mask

    def full_board_mask(self) -> CardMask:
        """
        Mask of all boards currently dealt.
        """

        mask = 0

        for card in self.node_cards:

            if card is not None:
                mask |= 1 << card

        return mask

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

            previous_bet = self.bet_to_call
            total = action.amount

            additional = total - player.current_bet

            player.stack -= additional
            player.current_bet = total
            player.total_contribution += additional

            self.pot += additional

            if player.stack == 0:
                player.is_all_in = True

            self.bet_to_call = total
            self.min_raise = total - previous_bet

            self.players_acted = 1
            self.last_aggressor = self.current_player
            self.raises_this_street += 1

            active = [
                i for i, p in enumerate(self.players)
                if not p.has_folded and not p.is_all_in
            ]

            idx = active.index(self.current_player)
            self.last_to_act = active[idx - 1]


    # -----------------------------------------------------
    # Betting round completion
    # -----------------------------------------------------

    def betting_round_complete(self):
        """
        Return True if the betting round is complete.
        - Only one player remaining: done
        - Otherwise, done if all remaining players are either:
        * folded
        * all-in
        * have matched the current bet
        """

        remaining = [
            p for p in self.players
            if not p.has_folded and not p.is_all_in
        ]

        # active = [p for p in remaining if not p.is_all_in]
        # remaining = self.remaining_players()

        if len(remaining) <= 1:
            return True

        if self.players_acted > 0 and self.current_player == self.last_to_act:
            return True
        # if all(p.current_bet == self.bet_to_call for p in remaining):
        #     if self.players_acted >= len(remaining):
        #         return True
            
        # for p in remaining:
        #     if not p.is_all_in and p.current_bet != self.bet_to_call:
        #         return False

        # if self.current_player == self.last_to_act:
        #     return True
            
        return False

    def betting_round_complete_after_action(self, acting_player):

        remaining = [p for p in self.players if not p.has_folded]

        if len(remaining) <= 1:
            return True
        
        for p in remaining:
            if not p.is_all_in and p.current_bet != self.bet_to_call:
                return False
            
        return acting_player == self.last_to_act

    def reset_betting_round(self):

        for p in self.players:
            p.current_bet = 0

        self.bet_to_call = 0
        self.min_raise = 0

        self.players_acted = 0
        self.last_aggressor = None
        self.raises_this_street = 0

        active = [
            i for i, p in enumerate(self.players)
            if not p.has_folded and not p.is_all_in
        ]

        if not active:
            self.last_to_act = None
            return
        
        start = self.current_player
        idx = active.index(start)

        self.last_to_act = active[idx - 1]

        # remaining = [i for i, p in enumerate(self.players) if not p.has_folded and not p.is_all_in]
        # self.last_to_act = remaining[-1] if remaining else None

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

    def legal_actions(self):

        p = self.players[self.current_player]

        # folded or all-in can't act
        if p.has_folded or p.is_all_in:
            return []
        
        to_call = self.bet_to_call - p.current_bet

        actions = [ActionType.FOLD]

        if to_call > 0:
            actions.append(ActionType.CALL)
        else:
            actions.append(ActionType.CHECK)

        if p.stack > to_call:

            if self.bet_to_call == 0:
                actions.append(ActionType.BET)
            else:
                if p.stack > to_call:
                    actions.append(ActionType.RAISE)

        print("Actions (engine): ", actions)

        return actions

            
