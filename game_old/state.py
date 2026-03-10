from dataclasses import dataclass
from typing import List
from cards.mask import CardMask
from .actions import ActionType

import random
from bindings.equity_wrapper import compute_equity

RANKS = "23456789TJQKA"
SUITS = "shdc"

class PokerState:
    WAITING_FOR_PLAYERS
    HAND_START
    POST_BLINDS
    DEAL_HOLE
    BETTING_ROUND
    DEAL_BOARD
    SHOWDOWN
    HAND_COMPLETE

    def __init__(self, players, game_def, scoring_engine):
        self.game = GameState(players)
        self.rules = game_def
        self.scoring_engine = scoring_engine

        self.phase = "WAITING"
    
    def start_hand(self):

        self.phase = "HAND_START"

        self.game.start_new_hand()

        self._post_blinds()
        self._deal_hole()

        self.phase = "BETTING"

@dataclass
class GameDefinition:
    hold_cards: int
    board_cards_per_street: list[int]
    max_board_cards: int
    score_types: list
    low_qualifier: int | None

@dataclass
class PlayerState:
    stack: int
    hand_mask: CardMask
    current_bet: int = 0
    has_folded: bool = False
    is_all_in: bool = False
    total_contribution: int = 0

class GameState:
    """
    Mutable core state.
    """

    __slots__ = (
        "players",
        "board_mask",
        "pot",
        "current_player",
        "dealer_position",
        "street",
        "deck_mask",
        "bet_to_call",
        "last_raise_size",
        "min_raise",
        "betting_round_complete",
        "last_aggressor",
        "players_acted",
        "raises_this_street",
        "small_blind",
        "big_blind",
        "hand_in_progress",
    )

    def __init__(self, players: List[PlayerState], deck_mask: int, small_blind: int, big_blind: int):
        self.players = players
        self.board_mask = 0
        self.pot = 0
        self.current_player = 0
        self.dealer_position = 0
        # self.street = 0 # 0=preflop, 1=flop, 2=turn, 3=river
        self.street_index: int
        self.street_structure: list[int]
        self.deck_mask = deck_mask
        self.bet_to_call = 0
        self.last_raise_size = 0
        self.min_raise = 0
        self.betting_round_complete = False
        self.last_aggressor = None
        self.players_acted = 0
        self.raises_this_street = 0
        self.small_blind = small_blind
        self.big_blind = big_blind
        self.hand_in_progress = False

    def apply_action(self, action):
        player = self.players[self.current_player]

        if action.type == ActionType.FOLD:
            player.has_folded = True
            self.players_acted += 1

        elif action.type == ActionType.CALL:
            to_call = self.bet_to_call - player.current_bet
            amount = min(to_call, player.stack)
            
            player.stack -= amount
            player.current_bet += amount
            self.pot += amount
            player.total_contribution += amount

            if player.stack == 0:
                player.is_all_in = True

            self.players_acted += 1

        elif action.type == ActionType.CHECK:
            self.players_acted += 1

        elif action.type in (ActionType.BET, ActionType.RAISE):
            to_call = self.bet_to_call - player.current_bet
            total = to_call + action.amount

            player.stack -= total
            player.current_bet += total
            self.pot += total
            player.total_contribution += total

            if player.stack == 0:
                player.is_all_in = True

            self.min_raise = action.amount
            self.bet_to_call = player.current_bet

            self.last_aggressor = self.current_player
            self.players_acted = 1
            self.raises_this_street += 1

        if self._betting_round_complete():
            self._end_betting_round()
        else:
            self._advance_turn()

    def start_new_hand(self):
        """
        Resets state and begins a new hand.
        """

        self.hand_in_progress = True
        self.street = 0
        self.board_mask = 0
        self.pot = 0
        self.bet_to_call = 0
        self.min_raise = 0
        self.players_acted = 0
        self.raises_this_street = 0
        self.last_aggressor = None

        # Rotate dealer
        self.dealer_position = (self.dealer_position + 1) % len(self.players)

        # Reset players
        for p in self.players:
            p.current_bet = 0
            p.has_folded = False
            p.is_all_in = False
            p.hand_mask = 0

        # Reset deck
        from cards.deck import FULL_DECK_MASK
        self.deck_mask = FULL_DECK_MASK

        self._post_blinds()
        self._deal_hole_cards()

        # First action preflop is left of big blind
        self.current_player = self._first_to_act_preflop()

    def _post_blinds(self):
        n = len(self.players)

        sb_pos = (self.dealer_position + 1) % n
        bb_pos = (self.dealer_position + 2) % n
        
        self._post_blind(sb_pos, self.small_blind)
        self._post_blind(bb_pos, self.big_blind)

        self.bet_to_call = self.big_blind
        self.min_raise = self.big_blind

    def _post_blind(self, player_index, amount):
        player = self.players[player_index]
        blind_amount = min(amount, player.stack)

        player.stack -= blind_amount
        player.current_bet += blind_amount
        self.pot += blind_amount
        player.total_contribution += blind_amount

        if player.stack == 0:
            player.is_all_in = True

    def _first_to_act_preflop(self):
        # Left of big blind
        n = len(self.players)
        return (self.dealer_position + 3) % n
    
    def _deal_hole_cards(self, num_cards):
        for _ in range(num_cards):
            if player.stack > 0:
                card = self._draw_card()
                player.hand_mask |= 1 << card

    def _draw_card(self):
        available = self.deck_mask
        lsb = available & -available # fast first bit
        card = lsb.bit_length() - 1
        self.deck_mask ^= lsb
        return card

    def _advance_turn(self):
        n = len(self.players)
        for i in range(1, n + 1):
            idx = (self.current_player + i) % n
            p = self.players[idx]
            if not p.has_folded and not p.is_all_in:
                self.current_player = idx
                return
            
    def _active_players(self):
        return [
            i for i, p in enumerate(self.players)
            if not p.has_folded and not p.is_all_in
        ]
    
    def _betting_round_complete(self) -> bool:
        remaining = [p for p in self.players if not p.has_folded]

        if len(remaining) <= 1:
            self._award_pot_to_last_player()
            return True
        
        active = self._active_players()
        
        # Everypne active has acted and no new raise
        if self.players_acted >= len(active):
            return True
        
        return False
    
    def _end_betting_round(self):
        # Reset player current bets:
        for p in self.players:
            p.current_bet = 0

        self.bet_to_call = 0
        self.min_raise = 0
        self.players_acted = 0
        self.raises_this_street = 0
        self.last_aggressor = None

        # Move to next street
        self.street += 1

        # If showdown street passed -> hand complete
        if self.street > 3: # Need to make this variable to allow for ocean
            self._resolve_showdown()
        else:
            self._start_next_street()

    def _start_next_street(self):
        self.street += 1

        cards_to_deal = self.street_structure[self.street_index]

        for i in range(cards_to_deal):
            self.board_mask |= 1 << self._draw_card()

        self._reset_betting_round()

        # self.current_player = self._first_to_act()

    def _first_to_act(self):
        n = len(self.players)
        for i in range(n):
            idx = (self.dealer_position + 1 + i) % n
            p = self.players[idx]
            if not p.has_folded and not p.is_all_in:
                return idx
        return 0
    
    def _award_pot_to_last_player(self):
        for p in self.players:
            if not p.has_folded:
                p.stack += self.pot
                break
        self.pot = 0
        self.hand_in_progress = False

    def _build_side_pots(self):
        """
        Returns list of (pot_amount, eligible_player_indices)
        """
        contributions = [
            (i, p.total_contribution)
            for i, p in enumerate(self.players)
            if p.total_contribution > 0
        ]

        if not contributions:
            return []
        
        # Sort by contribution ascending
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

    def _resolve_showdown(self):
        side_pots = self._build_side_pots()

        active_indices = [
            i for i, p in enumerate(self.players)
            if not p.has_folded
        ]

        player_masks = [
            self.players[i].hand_mask
            for i in active_indices
        ]

        ranks = self.scoring_engine.evaluate(
            player_masks,
            self.board_mask
        )

        for pot_amount, eligible in side_pots:

            contenders = [
                i for i in eligible
                if not self.players[i].has_folded
            ]

            if not contenders:
                continue

            contender_ranks = [
                ranks[active_indices.index(i)]
                for i in contenders
            ]

            best = max(contender_ranks)

            winners = [
                contenders[j]
                for j, r in enumerate(contender_ranks)
                if r == best
            ]

            self._distribute_pot(pot_amount, winners)


        # if len(active_players) == 1:
        #     self.players[active_players[0]].stack += self.pot
        #     self.pot = 0
        #     self.hand_in_progress = False
        #     return
        
        # side_pots = self._build_side_pots()

        # board_cards = self._mask_to_card_strings(self.board_mask)

        # for pot_amount, eligible in side_pots:
        #     contenders = [
        #         i for i in eligible
        #         if not self.players[i].has_folded
        #     ]

        #     if not contenders:
        #         continue

        #     hands = [
        #         self._mask_to_card_strings(self.players[i].hand_mask)
        #         for i in contenders
        #     ]

        #     result = compute_equity(
        #         hands,
        #         board_cards,
        #         exact=True,
        #         monte_carlo_samples=0,
        #         debug=False
        #     )

        #     equities = result["equities"]

        #     max_equity = max(equities)

        #     winners = [
        #         contenders[i]
        #         for i, eq in enumerate(equities)
        #         if eq == max_equity
        #     ]

        #     share = pot_amount // len(winners)
        #     remainder = pot_amount % len(winners)

        #     for w in winners:
        #         self.players[w].stack += share

        #     # distribute remainder by seat order
        #     for i in range(remainder):
        #         self.players[winners[i]].stack += 1

        # self.pot = 0
        # self.hand_in_progress = False    

    def _mask_to_card_strings(self, mask: int):
        cards = []
        for i in range(52):
            if mask & (1 << i):
                rank = RANKS[i % 13]
                suit = SUITS[i // 13]
                cards.append(rank + suit)
        return cards