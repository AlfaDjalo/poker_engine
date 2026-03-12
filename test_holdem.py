#!/usr/bin/env python3
"""
Complete end-to-end test for no-limit hold'em poker game.
Simulates a full hand from blinds through showdown.
"""

import random
from rules.game_definition import GameDefinition
from state.player_state import PlayerState
from state.poker_state import PokerState
from state.poker_state import Phase
from scoring.scoring_engine import CppScoringEngine
from rules.game_rules import GameRules
from actions.action import Action
from actions.action_type import ActionType
from cards.card_utils import mask_to_card_string

from poker_eval import ScoreType, ShowdownType

def print_game_state(poker_state, title=""):
    """Pretty-print current game state."""
    if title:
        print(f"\n{'='*60}")
        print(f"{title}")
        print('='*60)
    
    g = poker_state.game
    print(f"Phase: {poker_state.phase.name}")
    print(f"Street: {g.street_index} | Pot: {g.pot} | Bet to call: {g.bet_to_call}")
    
    board_str = mask_to_card_string(g.board_mask) or "(empty)"
    print(f"Board: {board_str} [{bin(g.board_mask)}]")
    
    for i, p in enumerate(g.players):
        status = "FOLDED" if p.has_folded else "ALL-IN" if p.is_all_in else "ACTIVE"
        marker = " <- current" if i == g.current_player else ""
        
        hand_str = mask_to_card_string(p.hand_mask) or "(empty)"
        print(
            f"  Player {i}: stack={p.stack:3d} | "
            f"hand={hand_str} | "
            f"current_bet={p.current_bet} | {status}{marker}"
        )


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
    
    # 15% chance of aggressive betting
    if random.random() < 0.15:
        g = poker_state.game
        player = g.players[g.current_player]
        to_call = g.bet_to_call - player.current_bet
        
        # Pot-sized bet/raise
        pot_size = g.pot
        aggressive_amount = pot_size
        
        for action in legal:
            if action.type == ActionType.BET and action.amount >= aggressive_amount:
                return action
            elif action.type == ActionType.RAISE and action.amount >= aggressive_amount:
                return action
    
    # Prefer CHECK > CALL > BET/RAISE(min) > FOLD
    for action_type in [ActionType.CHECK, ActionType.CALL]:
        for action in legal:
            if action.type == action_type:
                return action
    
    for action in legal:
        if action.type in (ActionType.BET, ActionType.RAISE):
            return action
    
    # Last resort: fold
    return next((a for a in legal if a.type == ActionType.FOLD), legal[0])


def street_name(street_index):
    """Return human-readable street name."""
    names = ["PREFLOP", "FLOP", "TURN", "RIVER"]
    return names[street_index] if street_index < len(names) else f"STREET_{street_index}"


def main():
    print("=" * 60)
    print("NO-LIMIT HOLD'EM - FULL HAND TEST")
    print("=" * 60)

    # Define the game: No-limit hold'em
    game_def = GameDefinition(
        hole_cards=2,
        board_cards_per_street=[3, 1, 1],  # Flop, turn, river
        score_types=[0],  # 0 for HIGH
        small_blind=1,
        big_blind=2,
        ante=0
    )

    # Create players
    players = [
        PlayerState(stack=100),
        PlayerState(stack=100),
        PlayerState(stack=100),
        PlayerState(stack=100),
    ]

    # Create scoring engine (C++ evaluator)
    scoring_engine = CppScoringEngine()

    # Create game rules
    rules = GameRules(
        score_types = [ScoreType.HIGH],
        showdown_type=ShowdownType.HOLDEM
    )

    # Create poker state
    poker_state = PokerState(players, game_def, rules, scoring_engine)

    # For this test, we need betting rules; import them
    from betting.betting_rules import NoLimitRules
    betting_rules = NoLimitRules()

    # Start the hand
    poker_state.start_hand()
    print_game_state(poker_state, "HAND STARTED - BLINDS POSTED, HOLE CARDS DEALT")

    # ===================================================================
    # Main hand loop: progress through betting rounds and board deals
    # ===================================================================

    while poker_state.phase != Phase.HAND_COMPLETE:

        if poker_state.phase == Phase.BETTING:

            g = poker_state.game
            street_label = street_name(g.street_index)
            
            print(f"\n{'-'*60}")
            print(f"BETTING ROUND: {street_label}")
            print(f"{'-'*60}")

            # Loop until betting round is complete
            while not poker_state.game.betting_round_complete():

                g = poker_state.game
                current = g.players[g.current_player]

                # Skip all-in and folded players
                if current.has_folded or current.is_all_in:
                    print(
                        f"Player {g.current_player}: "
                        f"{'FOLDED' if current.has_folded else 'ALL-IN'} (skipped)"
                    )
                    g.advance_turn()
                    continue

                # Select and apply action
                action = select_action(poker_state, betting_rules)

                if action:
                    print(
                        f"Player {g.current_player}: {action.type.name}({action.amount})"
                    )
                    poker_state.step(action)
                else:
                    print(f"Player {g.current_player}: (no legal actions)")
                    break

            # Check if hand is over (only 1 player left)
            if poker_state.phase == Phase.HAND_COMPLETE:
                print_game_state(
                    poker_state, 
                    f"{street_label} COMPLETE - WINNER BY FOLD"
                )
                break

            # Check if more streets to deal
            if poker_state._more_streets():
                poker_state._deal_next_board()
                poker_state.game.reset_betting_round()
                poker_state.game.current_player = poker_state._first_to_act()
                
                next_street = street_name(poker_state.game.street_index)
                board_str = mask_to_card_string(poker_state.game.board_mask)
                print_game_state(
                    poker_state, 
                    f"{next_street} - BOARD: {board_str}"
                )
            else:
                # Move to showdown
                print(f"\n{'-'*60}")
                print("SHOWDOWN")
                print(f"{'-'*60}")
                poker_state._resolve_showdown()
                poker_state.phase = Phase.HAND_COMPLETE

    # ===================================================================
    # Hand complete: print final results
    # ===================================================================

    print_game_state(poker_state, "HAND COMPLETE - FINAL STATE")

    print("\n" + "=" * 60)
    print("FINAL STACKS")
    print("=" * 60)
    for i, p in enumerate(players):
        print(f"Player {i}: {p.stack}")

    print("\n✓ Test completed successfully!")


if __name__ == "__main__":
    main()