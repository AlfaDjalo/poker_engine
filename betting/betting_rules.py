from abc import ABC, abstractmethod
from typing import List

from actions.action import Action
from actions.action_type import ActionType
from state.game_state import GameState


class BettingRules(ABC):

    @abstractmethod
    def legal_actions(self, state: GameState) -> List[Action]:
        pass


class NoLimitRules(BettingRules):

    def legal_actions(self, state: GameState) -> List[Action]:
        player = state.players[state.current_player]

        if player.has_folded or player.is_all_in:
            return []
        
        to_call = state.bet_to_call - player.current_bet
        actions = []

        # ------------------------------------------------
        # Fold / Call / Check
        # ------------------------------------------------

        if to_call > 0:

            actions.append(Action(ActionType.FOLD))
            actions.append(Action(ActionType.CALL, min(to_call, player.stack)))

        else:

            actions.append(Action(ActionType.CHECK))

        # ------------------------------------------------
        # Bet / Raise
        # ------------------------------------------------

        if player.stack > to_call:

            min_raise = max(state.min_raise, 1)
            max_raise = player.stack

            if to_call == 0:

                actions.append(Action(ActionType.BET, min_raise))
                actions.append(Action(ActionType.BET, max_raise))

            else:

                actions.append(Action(ActionType.RAISE, min_raise))
                actions.append(Action(ActionType.RAISE, max_raise))

        return actions
    

class PotLimitRules(BettingRules):

    def legal_actions(self, state: GameState) -> List[Action]:

        player = state.players[state.current_player]
   
        if player.has_folded or player.is_all_in:
            return []
        
        to_call = state.bet_to_call - player.current_bet
        actions = []

        if to_call > 0:

            actions.append(Action(ActionType.FOLD))
            actions.append(Action(ActionType.CALL, min(to_call, player.stack)))

        else:

            actions.append(Action(ActionType.CHECK))


        if player.stack > to_call:

            min_raise = max(state.min_raise, 1)

            max_raise = min(
                player.stack, 
                state.pot + 2 * to_call
            )
            
            if to_call == 0:
                actions.append(Action(ActionType.BET, min_raise))
                actions.append(Action(ActionType.BET, max_raise))

            else:

                actions.append(Action(ActionType.RAISE, min_raise))
                actions.append(Action(ActionType.RAISE, max_raise))

        return actions
    

class FixedLimitRules(BettingRules):

    def __init__(self, small_bet: int, big_bet: int, raise_cap: int = 4):

        self.small_bet = small_bet
        self.big_bet = big_bet
        self.raise_cap = raise_cap

    def _bet_size(self, state: GameState):

        if state.street_index < 2:
            return self.small_bet
        
        return self.big_bet


    def legal_actions(self, state: GameState) -> List[Action]:
        
        player = state.players[state.current_player]

        if player.has_folded or player.is_all_in:
            return []
        
        bet_size = self._bet_size(state)

        to_call = state.bet_to_call - player.current_bet
        
        actions = []

        if to_call > 0:

            actions.append(Action(ActionType.FOLD))
            actions.append(Action(ActionType.CALL, min(to_call, player.stack)))
        
        else:
        
            actions.append(Action(ActionType.CHECK))

        if state.raises_this_street < self.raise_cap:

            if to_call == 0:
            
                actions.append(Action(ActionType.BET, bet_size))

            else:

                actions.append(Action(ActionType.RAISE, bet_size))

        return actions