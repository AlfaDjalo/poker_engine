from abc import ABC, abstractmethod
from typing import List

from poker_engine.actions.action import Action
from poker_engine.actions.action_type import ActionType
from poker_engine.state.game_state import GameState


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


class AllInOrFoldRules(BettingRules):
    """
    Push-fold betting: the only actions ever offered are FOLD, and
    either CALL (if a bet is already out) or BET/RAISE sized to the
    player's ENTIRE remaining stack (a "shove") — no intermediate
    sizing is ever legal, matching the two-decision push-fold-duo
    curriculum stage the RL Lab trains against (SB: FOLD/ALL_IN,
    BB: FOLD/CALL — see RL_lab_integration_pushfoldduo.md).

    FIXED (see diagnose_action_space.py): CALL is only ever legal
    against an opponent who has ACTUALLY SHOVED ALL-IN (`facing_shove`
    below) — never against the forced blind alone. The previous version
    offered CALL whenever `to_call > 0`, with no distinction between
    "facing the forced big blind" and "facing a real shove" — this gave
    the player first to act (SB, facing only the posted big blind) an
    illegitimate limp option alongside FOLD/RAISE, training a
    fold/limp/shove three-way decision instead of this class's own
    documented fold/shove two-way decision. Confirmed empirically: SB's
    resolved options were [FOLD, CALL(1), RAISE(20)] at a 10bb stack
    instead of the intended [FOLD, RAISE(20)].

    This class is the plain-English specification other code
    (game_state.py's push-fold branch of legal_actions()/apply_action(),
    kept inline there for the same reason NoLimitRules/PotLimitRules
    aren't actually called from GameState.legal_actions() either — see
    that method's own logic) mirrors. It's also directly usable/testable
    on its own via the BettingRules interface.
    """

    def legal_actions(self, state: GameState) -> List[Action]:
        player = state.players[state.current_player]

        if player.has_folded or player.is_all_in:
            return []

        to_call = state.bet_to_call - player.current_bet
        shove_total = player.current_bet + player.stack  # entire stack, as a TOTAL bet
        actions = [Action(ActionType.FOLD)]

        facing_shove = any(
            i != state.current_player
            and p.is_all_in
            and p.current_bet == state.bet_to_call
            for i, p in enumerate(state.players)
        )

        if to_call > 0:
            if facing_shove:
                # Genuinely facing an opponent's shove — CALL (for
                # exactly what's left, if shorter-stacked) is legal.
                actions.append(Action(ActionType.CALL, min(to_call, player.stack)))
            if player.stack > to_call:
                # Facing a bet but can still shove for more (e.g. SB
                # open-shoves over the blind, or re-shoves over a
                # smaller all-in).
                actions.append(Action(ActionType.RAISE, shove_total))
            # else: not facing a real shove, and this player can't even
            # cover to_call by shoving (can't happen for equal starting
            # stacks, since to_call here is only ever the blind
            # difference — kept as a safety net for uneven-stack
            # variants) — FOLD is the only legal action, which is
            # already in `actions`.
        else:
            actions.append(Action(ActionType.CHECK))
            if player.stack > 0:
                actions.append(Action(ActionType.BET, shove_total))

        return actions