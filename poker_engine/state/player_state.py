from dataclasses import dataclass
from poker_engine.cards.mask import CardMask


@dataclass
class PlayerState:
    stack: int
    hand_mask: CardMask = 0

    current_bet: int = 0
    total_contribution: int = 0

    has_folded: bool = False
    is_all_in: bool = False

    # Distinct from has_folded. has_folded is a PER-HAND, transient
    # outcome (reset every hand by hand_session.start_new_hand()/
    # PokerState.start_hand()) that means "was dealt in, then gave up
    # this hand". sitting_out means "not dealt into this hand at all" --
    # no hole cards, never gets a turn, never a legal pass/discard
    # target, never posts a blind/ante -- while still occupying a
    # STABLE seat index across the session (so Backend seat/player_id
    # logging never has to renumber seats when someone busts or steps
    # away).
    #
    # NOT reset by hand_session.start_new_hand() -- unlike the other
    # per-hand fields on this dataclass, sitting_out is a session/
    # Backend-level decision (zero stack, or a player voluntarily
    # sitting out) that persists across hands until the Backend
    # explicitly changes it (e.g. once a player re-buys, or chooses to
    # sit back in). The Engine only ever reads it; it never sets it
    # for a player itself, except that a fresh PlayerState with
    # stack == 0 should generally be constructed with sitting_out=True
    # by whichever caller builds the player list for a hand.
    sitting_out: bool = False