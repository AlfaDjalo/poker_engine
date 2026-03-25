from enum import Enum
import random

from .game_state import GameState
from .player_state import PlayerState

from showdown.showdown_resolver import ShowdownResolver

from cards.deck import Deck #, FULL_DECK_MASK
from cards.mask import CardMask

# from board.board_generator import BoardGenerator
from board.board_enumerator import choose_k


class Phase(Enum):

    WAITING = 0
    HAND_START = 1
    BETTING = 2
    DEAL_BOARD = 3
    SHOWDOWN = 4
    HAND_COMPLETE = 5


class PokerState:

    def __init__(self, players, game_def, rules, scoring_engine):

        self.game = GameState(players)

        self.game_def = game_def
        self.rules = rules

        self.scoring_engine = scoring_engine

        self.deck = Deck()

        self.resolver = ShowdownResolver(scoring_engine, rules, debug=True)

        self.phase = Phase.WAITING

    # -----------------------------------------------------
    # Hand lifecycle
    # -----------------------------------------------------

    def start_hand(self):

        self.phase = Phase.HAND_START

        g = self.game

        g.street_index = 0
        # g.board_mask = 0
        g.pot = 0

        g.node_cards = [None] * self.game_def.node_count

        self.deck.shuffle()

        g.dealer_position = (g.dealer_position + 1) % len(g.players)

        for p in g.players:

            p.current_bet = 0
            p.total_contribution = 0
            p.has_folded = False
            p.is_all_in = False
            p.hand_mask = 0

        self._post_blinds()

        self._deal_hole_cards()

        g.current_player = self._first_to_act_preflop()
        g.last_to_act = (g.current_player - 1) % len(g.players)
        self.phase = Phase.BETTING

    # -----------------------------------------------------

    def step(self, action):

        if self.phase in (Phase.HAND_COMPLETE, Phase.WAITING):
            return

        g = self.game

        # ------------------------------------------------
        # Deal board phase
        # ------------------------------------------------

        if self.phase == Phase.DEAL_BOARD:

            if not self._more_streets():
                self._resolve_showdown()
                self.phase = Phase.HAND_COMPLETE
                return

            self._deal_next_board()

            g.current_player = self._first_to_act()

            g.reset_betting_round()


            self.phase = Phase.BETTING
            return

        g.apply_action(action)

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

                self.phase = Phase.HAND_COMPLETE
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

    def _deal_next_board(self):
        
        g = self.game
        
        # nodes = self.game_def.board_cards_per_street[g.street_index]
        nodes = self.game_def.street_nodes[g.street_index]

        for node in nodes:

            card = self.deck.draw_next()

            g.node_cards[node] = card

        g.street_index += 1

        # cards_to_deal = self.game_def.board_cards_per_street[g.street_index]  # <--- use game_def
        
        # dead_mask = g.board_mask

        # for p in g.players:
        #     dead_mask |= p.hand_mask

        # available = FULL_DECK_MASK & ~dead_mask

        # boards = list(choose_k(available, cards_to_deal))

        # new_cards = random.choice(boards)

        # g.board_mask |= new_cards

        # g.street_index += 1

        # for _ in range(cards):
        #     card = self.deck.draw_next()
        #     g.board_mask |= 1 << card
        # g.street_index += 1


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

        for p in g.players:

            if not p.has_folded:

                p.stack += g.pot

                g.pot = 0

                return

    # -----------------------------------------------------
    # Showdown
    # -----------------------------------------------------

    def _resolve_showdown(self):

        print("SHOWDOWN")
        print("board:", self.game.node_cards)
        print("players:", [p.hand_mask for p in self.game.players])

        self.last_showdown = self.resolver.resolve(self.game)


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