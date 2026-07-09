from enum import Enum
import random

from .game_state import GameState
from .player_state import PlayerState
from .hand_snapshot import HandSnapshot, PlayerSnapshot

from showdown.showdown_resolver import ShowdownResolver

from cards.deck import Deck
from cards.mask import CardMask, mask_to_card_ids

from board.board_enumerator import choose_k


class Phase(Enum):

    WAITING = 0
    HAND_START = 1
    BETTING = 2
    DEAL_BOARD = 3
    SHOWDOWN = 4
    HAND_COMPLETE = 5


class PokerState:

    def __init__(
            self, 
            players, 
            game_def, 
            rules, 
            scoring_engine,
            callbacks=None
    ):

        self.game = GameState(players)

        self.game_def = game_def
        self.rules = rules

        self.scoring_engine = scoring_engine

        self.deck = Deck()

        self.resolver = ShowdownResolver(scoring_engine, rules, debug=True)

        self.phase = Phase.WAITING

        self.callbacks = callbacks

    # -----------------------------------------------------
    # Hand lifecycle
    # -----------------------------------------------------

    def start_hand(self):

        self.phase = Phase.HAND_START

        g = self.game

        g.street_index = 0
        g.pot = 0

        g.node_cards = [None] * self.game_def.node_count
        g.discard_pile = []

        self.deck.shuffle()
        g.dealer_position = (g.dealer_position + 1) % len(g.players)

        for p in g.players:

            p.current_bet = 0
            p.total_contribution = 0
            p.has_folded = False
            p.is_all_in = False
            p.hand_mask = 0

        self._post_antes()
        self._post_blinds()

        self._deal_hole_cards()
        self._deal_next_board()

        g.current_player = self._first_to_act_preflop()
        g.last_to_act = (g.current_player - 1) % len(g.players)
        self.phase = Phase.BETTING

        if self.callbacks:
            self.callbacks.on_hand_start(self)

    
    # -----------------------------------------------------
    # Load State (Hand Editor)
    # -----------------------------------------------------

    @classmethod
    def load_state(cls,
        snapshot: HandSnapshot,
        game_def,
        rules,
        scoring_engine,
        callbacks=None
        ) -> "PokerState":
        """
        Reconstruct a PokerState from a HandSnapshot.
        Used by the hand editor to resume play from an arbitrary point.
        Does NOT call start_hand() — state is already mid-hand.
        """
        players = [
            PlayerState(
                stack=ps.stack,
                hand_mask=ps.hand_mask,
                current_bet=ps.current_bet,
                total_contribution=ps.total_contribution,
                has_folded=ps.has_folded,
                is_all_in=ps.is_all_in,
                
            )
            for ps in snapshot.players
        ]

        instance = cls(players, game_def, rules, scoring_engine, callbacks)

        g = instance.game

        # Restore game state fields
        g.street_index = snapshot.street_index
        g.pot = snapshot.pot
        g.dealer_position = snapshot.dealer_position
        g.current_player = snapshot.current_player
        g.bet_to_call = snapshot.bet_to_call
        g.min_raise = snapshot.min_raise
        g.raises_this_street = snapshot.raises_this_street
        g.last_aggressor = snapshot.last_aggressor
        g.node_cards = snapshot.node_cards
        g.discard_pile = snapshot.discard_pile

        if g.street_index < len(game_def.street_nodes):
            current_street_nodes = game_def.street_nodes[g.street_index]
            # If all nodes for this street have a card, the engine already dealt it!
            if all(g.node_cards[n] is not None for n in current_street_nodes):
                g.street_index += 1

        # Recompute last_to_act from active player list
        active = [
            i for i, p in enumerate(g.players)
            if not p.has_folded and not p.is_all_in
        ]

        if active and g.current_player not in active:
            raise ValueError(
                f"Invalid state: current_player {g.current_player} "
                f"is not among the active players {active}."
            )

        if active:
            start = g.current_player
            if start in active:
                idx = active.index(start)
            else:
                idx = 0
            g.last_to_act = active[idx - 1]
        else:
            g.last_to_act = None

        # Reconstruct deck: full deck minus in-play and discard
        in_play = set(snapshot.discard_pile)
        for card in snapshot.node_cards:
            if card is not None:
                in_play.add(card)
        for ps in snapshot.players:
            for card in mask_to_card_ids(ps.hand_mask):
                in_play.add(card)

        instance.deck.shuffle()
        for card in in_play:
            instance.deck.remove(card)

        instance.phase = Phase.BETTING

        return instance

    # -----------------------------------------------------
    # Draw game helpers
    # -----------------------------------------------------

    def _reshuffle_discard(self):
        """Reshuffle discard pile back into deck (draw games)."""
        for card in self.game.discard_pile:
            self.deck.return_card(card)
        self.game.discard_pile = []
        self.deck.shuffle()

    # -----------------------------------------------------
    # step(), dealing, blinds, turn order, showdown
    # (unchanged from original — reproduced for completeness)
    # -----------------------------------------------------

    def step(self, action):

        if self.phase in (Phase.HAND_COMPLETE, Phase.WAITING):
            return

        g = self.game

        # Commenting this out to let GameService control progression
        # if self.phase == Phase.SHOWDOWN:
        #     self.phase = Phase.HAND_COMPLETE
        #     return

        # ------------------------------------------------
        # Deal board phase
        # ------------------------------------------------

        if self.phase == Phase.DEAL_BOARD:

            if not self._more_streets():
                self._resolve_showdown()
                self.phase = Phase.SHOWDOWN
                return

            self._deal_next_board()

            g.current_player = self._first_to_act()

            g.reset_betting_round()


            self.phase = Phase.BETTING
            return

        pot_before = g.pot
        stack_before = g.players[g.current_player].stack

        player_index = g.current_player
        g.apply_action(action)

        if self.callbacks and action is not None:
            self.callbacks.on_action(self, action, player_index, pot_before, stack_before)

        if g.betting_round_complete():

            if self._only_one_player_left():

                self._award_last_player()

                self.phase = Phase.HAND_COMPLETE
                return

            if self._more_streets():

                self.phase = Phase.DEAL_BOARD
                return

            else:

                self._resolve_showdown()

                self.phase = Phase.SHOWDOWN
                return

        else:

            g.advance_turn()

    # -----------------------------------------------------
    # Dealing
    # -----------------------------------------------------

    def _deal_hole_cards(self):

        g = self.game

        for _ in range(self.game_def.hole_cards):

            for p in g.players:

                if p.stack > 0:

                    card = self.deck.draw_next()

                    p.hand_mask |= 1 << card

    def _deal_initial_board(self):
        """Deal street 0 nodes at hand start (e.g. bomb pot flop)."""
        g = self.game
        nodes = self.game_def.street_nodes[0]
        for node in nodes:
            card = self.deck.draw_next()
            g.node_cards[node] = card

        g.street_index = 1



    def _deal_next_board(self):
        g = self.game
        nodes = self.game_def.street_nodes[g.street_index]
        for node in nodes:
            card = self.deck.draw_next()
            g.node_cards[node] = card
        g.street_index += 1


    # -----------------------------------------------------
    # Board helpers
    # -----------------------------------------------------

    def get_node_mask(self, nodes):
        """
        Convert node indices to a CardMask.
        """

        g = self.game

        mask = 0

        for n in nodes:

            card = g.node_cards[n]

            if card is not None:

                mask |= 1 << card

        return mask

    # -----------------------------------------------------
    # Blinds
    # -----------------------------------------------------

    def _post_blinds(self):

        g = self.game

        n = len(g.players)

        sb = (g.dealer_position + 1) % n
        bb = (g.dealer_position + 2) % n

        self._post_blind(sb, self.game_def.small_blind)
        self._post_blind(bb, self.game_def.big_blind)

        g.bet_to_call = self.game_def.big_blind
        g.min_raise = self.game_def.big_blind

    def _post_blind(self, index, amount):

        g = self.game

        player = g.players[index]

        blind = min(amount, player.stack)

        player.stack -= blind

        player.current_bet += blind
        player.total_contribution += blind

        g.pot += blind

        if player.stack == 0:

            player.is_all_in = True

    def _post_antes(self):

        g = self.game
        amount = self.game_def.ante

        for player in g.players:
            ante = min(amount, player.stack)
            player.stack -= ante
            player.current_bet += ante
            player.total_contribution += ante
            g.pot += ante

            if player.stack == 0:
                player.is_all_in = True

    # -----------------------------------------------------
    # Turn order
    # -----------------------------------------------------

    def _first_to_act_preflop(self):

        g = self.game
        n = len(g.players)

        return (g.dealer_position + 3) % n

    def _first_to_act(self):

        g = self.game
        n = len(g.players)

        for i in range(n):

            idx = (g.dealer_position + 1 + i) % n

            p = g.players[idx]

            if not p.has_folded and not p.is_all_in:

                return idx

        return 0

    # -----------------------------------------------------
    # Hand completion
    # -----------------------------------------------------

    def _only_one_player_left(self):

        g = self.game

        active = [

            p for p in g.players

            if not p.has_folded

        ]

        return len(active) == 1

    def _award_last_player(self):

        g = self.game

        for i, p in enumerate(g.players):

            if not p.has_folded:

                p.stack += g.pot

                self.last_showdown = None
                self.last_winners = [i]

                g.pot = 0

                return

    # -----------------------------------------------------
    # Showdown
    # -----------------------------------------------------

    def _resolve_showdown(self):

        print("SHOWDOWN")
        print("board:", self.game.node_cards)
        print("players:", [p.hand_mask for p in self.game.players])

        result = self.resolver.resolve(self.game)

        self.last_showdown = result

        self.last_winners = [
            p for p, amt in result.payouts.items()
            if amt > 0
        ]

        self.game.pot = 0

        if self.callbacks:
            self.callbacks.on_showdown(self, result)

        # self.last_showdown = self.resolver.resolve(self.game)


    def _distribute_pot(self, pot, winners):

        g = self.game

        share = pot // len(winners)

        remainder = pot % len(winners)

        for w in winners:

            g.players[w].stack += share

        for i in range(remainder):

            g.players[winners[i]].stack += 1

    # -----------------------------------------------------

    def _more_streets(self):
        # return self.game.street_index < len(self.game_def.board_cards_per_street)
        return self.game.street_index < len(self.game_def.street_nodes)
    
    # def _more_streets(self) -> bool:
    #     g = self.game
    #     # Ensure we don't advance past the absolute maximum number of configured streets
    #     if g.street_index >= len(self.game_def.street_nodes) - 1:
    #         return False
            
    #     # Alternate safety: If all board cards for the entire game definition are already dealt, 
    #     # there are physically no more streets to deal.
    #     total_expected_board = sum(self.game_def.board_cards_per_street)
    #     if len(g.board) >= total_expected_board:
    #         return False

    #     return True

    def _fire_forced_bet_callbacks(self, stacks_before):
        g = self.game
        n = len(g.players)
        pot_running = 0

        # Antes (posted in player order)
        if self.game_def.ante > 0:
            for i, p in enumerate(g.players):
                amount = min(self.game_def.ante, stacks_before[i])
                if amount > 0:
                    action = Action(type=ActionType.ANTE, amount=amount)
                    self.callbacks.on_action(
                        self, action, i,
                        pot_before=pot_running,
                        stack_before=stacks_before[i]
                    )
                    pot_running += amount

        # Small blind
        sb = (g.dealer_position) % n   # dealer_position already incremented
        sb_amount = min(self.game_def.small_blind, stacks_before[sb])
        if sb_amount > 0:
            action = Action(type=ActionType.BLIND, amount=sb_amount)
            self.callbacks.on_action(
                self, action, sb,
                pot_before=pot_running,
                stack_before=stacks_before[sb]
            )
            pot_running += sb_amount

        # Big blind
        bb = (g.dealer_position + 1) % n
        bb_amount = min(self.game_def.big_blind, stacks_before[bb])
        if bb_amount > 0:
            action = Action(type=ActionType.BLIND, amount=bb_amount)
            self.callbacks.on_action(
                self, action, bb,
                pot_before=pot_running,
                stack_before=stacks_before[bb]
            )