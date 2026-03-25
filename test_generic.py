#!/usr/bin/env python3
"""
Complete end-to-end test for generic poker game.
Simulates a full hand from blinds through showdown.
"""

import random

from state.player_state import PlayerState
from state.poker_state import PokerState, Phase

from scoring.scoring_engine import CppScoringEngine

from actions.action_type import ActionType

from cards.card_utils import mask_to_card_string

from games.loader import load_game

from betting.betting_rules import NoLimitRules, PotLimitRules

from display.board_display import format_cap_boards

# GAME = "holdem"
# GAME = "omaha"
GAME = "plo8"
# GAME = "double_board_plo_bomb_pot"


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

def street_name(index):
    names = ["PREFLOP", "FLOP", "TURN", "RIVER", "OCEAN"]
    if index < len(names):
        return names[index]
    return f"STREET_{index}"


def board_string(game):

    cards = []

    for c in game.node_cards:
        if c is not None:
            cards.append(c)
    
    if not cards:
        return "(no board)"
    
    mask = 0
    for c in cards:
        mask |= 1 << c

    return mask_to_card_string(mask)


# ------------------------------------------------------------
# Street summary printer
# ------------------------------------------------------------

def print_street_summary(poker_state, label):

    g = poker_state.game

    print("\n" + "=" * 70)
    print(f"{label}")
    print("\n" + "=" * 70)

    print(f"Street: {street_name(g.street_index)}")
    print(f"Pot: {g.pot}")

    print(format_cap_boards(g.node_cards))
    # print(f"Board: {board_string(g)}")
    print()

    for i, p in enumerate(g.players):
        
        hand = mask_to_card_string(p.hand_mask) or "(empty)"

        status = "ACTIVE"
        if p.has_folded:
            status = "FOLDED"
        elif p.is_all_in:
            status = "ALL-IN"

        print(
            f"Player {i}: "
            f"stack={p.stack:3d} | "
            f"bet={p.current_bet:3d} | "
            f"{status:7s} | "
            f"hand={hand}"
        )

    print("=" * 70)
    print()



# def print_game_state(poker_state, title=""):
#     """Pretty-print current game state."""
#     if title:
#         print(f"\n{'='*60}")
#         print(f"{title}")
#         print('='*60)
    
#     g = poker_state.game

#     print("\n" + "="*60)
#     print(f"Phase: {poker_state.phase.name}")
#     print(f"Street: {g.street_index}")
#     print(f"Pot: {g.pot}")
#     print("\n" + "="*60)

#     if hasattr(g, "board_mask"):

#         board = mask_to_card_string(g.board_mask)
#         print("Board:", board)

#     elif hasattr(g, "node_cards"):

#         print("Nodes:", g.node_cards)
    
#     for i, p in enumerate(g.players):

#         hand = mask_to_card_string(p.hand_mask)

#         status = "FOLDED" if p.has_folded else "ALL-IN" if p.is_all_in else "ACTIVE"

#         print(
#             f"  Player {i}: stack={p.stack:3d} | "
#             f"bet={p.current_bet} | "
#             f"{status} |"
#             f"{hand}"
#         )

# ------------------------------------------------------------
# Action selection
# ------------------------------------------------------------

def select_action(poker_state, betting_rules):
    """
    Select an action for the current player.
    Uses a simple heuristic with occasional aggressive betting.
    - 10-20% chance: make a pot-sized bet/raise
    - Otherwise: prefer CHECK > CALL > fold
    """
    legal = betting_rules.legal_actions(poker_state.game)
    
    if not legal:
        return None
    
    g = poker_state.game
    player = g.players[g.current_player]
    
    to_call = g.bet_to_call - player.current_bet
    facing_bet = to_call > 0
    
    r = random.random()

    # ------------------------------------------------
    # Facing a bet
    # ------------------------------------------------
         
    if facing_bet:

        if r < 0.15:
            for a in legal:
                if a.type == ActionType.RAISE:
                    return a
                
        elif r < 0.40:
            for a in legal:
                if a.type == ActionType.FOLD:
                    return a
                
        else:
            for a in legal:
                if a.type == ActionType.CALL:
                    return a
                
        for pref in [ActionType.CALL, ActionType.FOLD]:
            for a in legal:
                if a.type == pref:
                    return a
                
    # ------------------------------------------------
    # Not facing a bet
    # ------------------------------------------------

    else:

        if r < 0.15:
            for a in legal:
                if a.type == ActionType.BET:
                    return a

        for a in legal:
            if a.type == ActionType.CHECK:
                return a

        return legal[0]


def debug_state(g):

    print("\nDEBUG STATE")
    print("street_index:", g.street_index)
    print("bet_to_call:", g.bet_to_call)
    print("pot:", g.pot)
    print("node_cards:", g.node_cards)

    for i,p in enumerate(g.players):
        print(
            i,
            "bet:",p.current_bet,
            "stack:",p.stack,
            "folded:",p.has_folded
        )

def main():

    print("=" * 60)
    print("\nRunning game:", GAME)
    print("=" * 60)

    game_def, rules = load_game(GAME)

    # Create players
    players = [
        PlayerState(stack=100),
        PlayerState(stack=100),
        PlayerState(stack=100),
        PlayerState(stack=100),
    ]

    # Create scoring engine (C++ evaluator)
    scoring_engine = CppScoringEngine()

    # Create poker state
    poker_state = PokerState(players, game_def, rules, scoring_engine)

    if game_def.betting_type == "no_limit":
        betting_rules = NoLimitRules()
    else:
        betting_rules = PotLimitRules()

    # Start the hand
    poker_state.start_hand()

    print_street_summary(poker_state, "HAND STARTED - BLINDS POSTED, HOLE CARDS DEALT")

    # ===================================================================
    # Main hand loop: progress through betting rounds and board deals
    # ===================================================================

    while poker_state.phase != Phase.HAND_COMPLETE:

        if poker_state.phase == Phase.DEAL_BOARD:

            poker_state.step(None)

            print_street_summary(
                poker_state,
                f"{street_name(poker_state.game.street_index)} DEALT"
            )

            continue

        # ------------------------------------------------
        # Betting phase
        # ------------------------------------------------
        
        if poker_state.phase == Phase.BETTING:

            g = poker_state.game

            print(f"\n--- Betting round: {street_name(g.street_index)} ---\n")
            
            while poker_state.phase == Phase.BETTING:
                    
                player = g.players[g.current_player]
                
                if player.has_folded or player.is_all_in:
                    
                    poker_state.step(None)
                    # g.advance_turn()
                    continue
            
                action = select_action(poker_state, betting_rules)

                if action:

                    amount = f" {action.amount}" if action.amount else ""

                    print(
                        f"Player {g.current_player}: "
                        f"{action.type.name} {amount}"
                    )

                    poker_state.step(action)

                    print(format_cap_boards(g.node_cards))
                    # print("Board:", board_string(g))
                    print("Pot:", g.pot)

            print_street_summary(
                poker_state,
                f"END OF {street_name(g.street_index)} BETTING"
            )

            # debug_state(g)
            
            # if poker_state.phase == Phase.HAND_COMPLETE:
            #     break
                    
            # if poker_state._more_streets():

            #     print("DEBUG streets:", poker_state.game.street_index)
            #     print("DEBUG board:", poker_state.game.node_cards)
            #     print("DEBUG more streets:", poker_state._more_streets())

            #     poker_state._deal_next_board()

            #     poker_state.game.reset_betting_round()

            #     poker_state.game.current_player = poker_state._first_to_act()

            #     print_street_summary(
            #         poker_state,
            #         f"{street_name(poker_state.game.street_index)} DEALT"
            #     )

            # else:

            #     poker_state._resolve_showdown()

            #     poker_state.phase = Phase.HAND_COMPLETE
            
    # ===================================================================
    # Hand complete: print final results
    # ===================================================================

    print_street_summary(
        poker_state,
        "HAND COMPLETE — FINAL STATE"
    )

    print("\n" + "=" * 60)
    print("FINAL STACKS")
    print("=" * 60)

    for i, p in enumerate(players):
        print(f"Player {i}: {p.stack}")

    print("\n✓ Test completed successfully!")


if __name__ == "__main__":
    main()