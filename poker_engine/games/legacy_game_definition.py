# poker_engine/games/legacy_game_definition.py
"""
LegacyGameDefinition: the GameDefinition shape PokerState (and its two
current RL Lab callers, push_fold_service.py / trainer_service.py)
actually reads at runtime -- kept deliberately separate from
poker_engine.rules.game_definition.GameDefinition (the graph-native
shape GameService/GraphEngine use). See that module's own docstring for
why hole_cards/betting_type/blinds/ante/street_nodes were removed FROM
THAT class specifically, and CAP_Technical_Quick_Reference.md §12.4.

Attribute list below is exhaustive against everywhere PokerState reads
game_def, traced through its full lifecycle:

  __init__              -> betting_type
  start_hand              -> node_count
  _deal_hole_cards          -> hole_cards
  _post_antes                -> ante
  _post_blinds                 -> small_blind, big_blind
  _deal_next_board /
  _deal_initial_board /
  _more_streets /
  load_state (Hand Editor)       -> street_nodes

street_names isn't read by PokerState itself but is kept for parity
with the pre-graph schema and for any caller (session logging, RL Lab
scenario display) that wants street labels without re-deriving them.

score_types / layout_name are carried through unchanged for anything
that inspects a GameDefinition generically regardless of which loader
produced it.
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class LegacyGameDefinition:
    game_name: str
    node_count: int
    score_types: List

    layout_name: Optional[str] = None

    hole_cards: int = 0
    small_blind: int = 0
    big_blind: int = 0
    ante: int = 0
    betting_type: str = "no_limit"
    street_nodes: List[List[int]] = field(default_factory=list)
    street_names: List[str] = field(default_factory=list)