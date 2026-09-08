from typing import Iterable, List
from poker_engine.cards.deck import FULL_DECK_MASK
from poker_engine.cards.mask import CardMask, mask_to_card_ids
from .player_state import PlayerState
from poker_engine.actions.action_type import ActionType


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
        "discard_pile",
        "betting_type",
    )

    def __init__(self, players: List[PlayerState], betting_type: str = "no_limit"):

        self.players = players
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
        self.discard_pile: List[int] = []
        # Drives legal_actions()/apply_action() branching below. Set from
        # GameDefinition.betting_type by PokerState.__init__ (see
        # poker_state.py) so it never needs to be threaded through every
        # call site individually. "push_fold" restricts betting to
        # FOLD / CALL / full-stack shove only — see AllInOrFoldRules in
        # betting_rules.py for the reference spec this mirrors.
        self.betting_type = betting_type

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
            if not p.has_folded and not p.is_all_in and not p.sitting_out:
                self.current_player = idx
                return

    def active_players(self):
        # not folded, not all-in, and actually dealt into this hand
        # (see PlayerState.sitting_out's own docstring for why this is
        # a separate, persistent flag rather than removing the seat
        # from self.players entirely).
        return [
            i for i, p in enumerate(self.players)
            if not p.has_folded and not p.is_all_in and not p.sitting_out
        ]

    def remaining_players(self):
        # not folded and actually dealt into this hand. A sitting-out
        # seat was never dealt cards, so it can never be "still in the
        # hand" regardless of has_folded's value.
        return [
            i for i, p in enumerate(self.players)
            if not p.has_folded and not p.sitting_out
        ]

    # -----------------------------------------------------
    # Betting logic
    # -----------------------------------------------------

    def apply_action(self, action):

        player = self.players[self.current_player]

        if action.type == ActionType.FOLD:

            for card_id in mask_to_card_ids(player.hand_mask):
                self.discard_pile.append(card_id)
            player.hand_mask = 0

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

            # Push-fold: the only ever legal BET/RAISE is a full shove.
            # Clamp here (rather than trusting the caller's amount) so a
            # wrong/stale amount from an API caller can never leave chips
            # behind or shove for more than the player actually has.
            if self.betting_type == "push_fold":
                total = player.current_bet + player.stack

            # River-only: trust the caller's amount. TrainerService's
            # _build_engine_action() already computes the correct total
            # for every sizing mode this betting_type can see —
            # sizing:"pot" (pot_fraction * pot, capped at stack) or
            # sizing:"stack" (a true full shove, current_bet + stack) —
            # both already capped at the player's actual stack, so there
            # is nothing left for the engine to re-derive here.
            #
            # This branch USED TO unconditionally override to
            # min(pot, current_bet + stack), on the assumption every
            # river bet was pot-sized (sizing:"pot" at pot_fraction 1.0,
            # which made this override a no-op). Once river_duo's "bet"
            # action_map entry was changed to sizing:"stack" (a real
            # all-in, see training_config.yaml), this override silently
            # re-capped every "all-in" shove down to the pot size
            # whenever stack > pot — e.g. a 100bb (200-chip) stack
            # against a 100-chip pot only ever committed 100 chips,
            # leaving 100 chips uncommitted behind on BOTH sides of the
            # street despite the action being labeled/graded as all-in.
            # The betting round still completed correctly either way
            # (no re-raises are ever legal here — see legal_actions()
            # below), but the actual chips moved didn't match what the
            # UI/policy believed had happened.
            #
            # single_bet (holdem_full_duo / omaha_full_duo): same
            # "trust the caller" treatment as river_only — TrainerService
            # already caps every sizing mode at the player's stack before
            # this is ever called, and single_bet's whole point (like
            # river_only) is exactly one bet/raise per street, so there
            # is nothing for the engine to re-derive here either.

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

            # idx = active.index(self.current_player)
            # self.last_to_act = active[idx - 1]

            if self.current_player in active:
                idx = active.index(self.current_player)
                self.last_to_act = active[idx - 1]
            else:
                self.last_to_act = active[-1] if active else None


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
            if not p.has_folded and not p.is_all_in and not p.sitting_out
        ]

        if not remaining:
            return True

        if len(remaining) == 1:
            # The single player who still has chips behind still needs to
            # act if their current bet hasn't matched bet_to_call yet (e.g.
            # an opponent just shoved all-in and this player hasn't
            # responded). Only treat the round as complete once they've
            # actually matched — otherwise their call/fold decision would
            # be skipped entirely.
            return remaining[0].current_bet == self.bet_to_call

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

        active = self.active_players()

        if not active:
            self.last_to_act = None
            return

        # current_player may be the player who JUST folded to close out
        # the previous street's betting (their fold was the action that
        # made betting_round_complete() true) -- they're no longer in
        # `active`, so a plain active.index(current_player) would raise
        # ValueError. Walk forward seat-by-seat from current_player to
        # the next ACTUALLY-active seat instead of assuming
        # current_player is still a member of `active` -- with nobody
        # folded/all-in this reduces to exactly the old
        # active.index(current_player) behaviour, so no other caller's
        # behaviour changes.
        n = len(self.players)
        start = self.current_player
        idx = None
        for offset in range(n):
            candidate = (start + offset) % n
            if candidate in active:
                idx = active.index(candidate)
                break

        # Unreachable: `active` is non-empty (checked above), so some
        # seat in range(n) must be in it -- idx is always set by the
        # loop. Guarded anyway rather than trusting that invariant
        # silently.
        if idx is None:
            idx = 0

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

        # ------------------------------------------------
        # Push-fold: only FOLD, and either CALL (facing a shove) or a
        # full-stack shove of its own — never an intermediate size.
        # Mirrors AllInOrFoldRules.legal_actions() in betting_rules.py.
        # ------------------------------------------------
        if self.betting_type == "push_fold":
            actions = [ActionType.FOLD]

            if to_call > 0:
                actions.append(ActionType.CALL)
                if p.stack > to_call:
                    actions.append(ActionType.RAISE)
            else:
                actions.append(ActionType.CHECK)
                if p.stack > 0:
                    actions.append(ActionType.BET)

            return actions

        # ------------------------------------------------
        # River-only: single pot-sized bet, no re-raises. FOLD is
        # always offered; CHECK/BET when nothing is owed, CALL only
        # (never a re-raise) when facing the one bet this street can
        # ever have. Mirrors push_fold's shape exactly, sized to the
        # pot instead of the stack — see river.yaml / river_only clamp
        # in apply_action() above.
        # ------------------------------------------------
        if self.betting_type == "river_only":
            actions = [ActionType.FOLD]

            if to_call > 0:
                actions.append(ActionType.CALL)
            else:
                actions.append(ActionType.CHECK)
                if p.stack > 0:
                    actions.append(ActionType.BET)

            return actions

        # ------------------------------------------------
        # single_bet: exactly one voluntary bet/raise allowed per
        # street (holdem_full_duo / omaha_full_duo), then call/fold
        # only for the rest of that street. Differs from river_only
        # above in what it uses to detect "facing a bet": river_only
        # infers that purely from to_call > 0, which is safe there
        # because river_duo-style scenarios never post blinds (they
        # start from a randomized dead pot). single_bet's scenarios DO
        # post real blinds preflop, so to_call > 0 at the start of a
        # street can mean "nobody has voluntarily bet yet, this is
        # just the blind gap" (preflop) rather than "someone already
        # bet". raises_this_street (reset to 0 every street by
        # reset_betting_round(), only ever incremented by an actual
        # BET/RAISE above) is what actually distinguishes the two
        # cases.
        # ------------------------------------------------
        if self.betting_type == "single_bet":
            if self.raises_this_street == 0:
                actions = [ActionType.FOLD]
                if to_call > 0:
                    actions.append(ActionType.CALL)
                else:
                    actions.append(ActionType.CHECK)
                if p.stack > to_call:
                    actions.append(ActionType.BET if self.bet_to_call == 0 else ActionType.RAISE)
                return actions

            # Someone has already bet/raised this street — no more
            # sizing/re-raising, call or fold only (mirrors river_only
            # facing-a-bet exactly).
            actions = [ActionType.FOLD]
            if to_call > 0:
                actions.append(ActionType.CALL)
            else:
                actions.append(ActionType.CHECK)
            return actions

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

        return actions