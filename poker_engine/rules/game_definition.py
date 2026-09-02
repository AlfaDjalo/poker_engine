from dataclasses import dataclass
from typing import List, Optional


@dataclass
class GameDefinition:
    """
    Variant-level facts that live OUTSIDE the graph -- board layout size
    and scoring category set. Everything that used to live here (hole
    card count, per-street board counts, betting type/blinds/ante) is
    now flow-step config, expressed once in the variant's YAML `flow:`
    list, not duplicated onto this dataclass -- see flow_loader.py.
    Keeping it here as well would mean two representations of the same
    fact that could silently drift apart.
    """

    game_name: str
    node_count: int          # size of the board's node_cards array
    score_types: List        # poker_eval.ScoreType values used by this variant's points

    layout_name: Optional[str] = None   # e.g. "double_board" -- informational only