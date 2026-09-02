"""
poker_engine/graph/core_types.py

Core decision types for the graph-based game engine.

A "Decision" is the single abstraction through which every player choice
flows -- betting actions AND hand-move choices (discard, draw, pass the
trash, yes/no calls like Grinch's Christmas trigger, or arbitrary
enumerated choices) are all Decisions. This is deliberate: AI models, the
hand-creation UI, and replay logging all interact with exactly one shape --
"here is the decision on offer (DecisionRequest), here are the legal
options, here is what was chosen (DecisionResponse)" -- regardless of
which kind of decision it is. Nothing downstream needs variant-specific
plumbing; only the DecisionDomain distinguishes them, and only inside the
one resolver that actually implements that domain's semantics.

This module has no dependency on the graph structure itself (Node,
Transition, Condition) or on GameState -- it only defines the vocabulary
those modules build on.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, Optional, Tuple, Union

from poker_engine.actions.action_type import ActionType


# ---------------------------------------------------------------------
# Decision domains
# ---------------------------------------------------------------------

class DecisionDomain(Enum):
    """
    The kind of choice being offered at a DECISION node.

    Every domain resolves to the same DecisionRequest/DecisionResponse
    envelope; only the option payload and the chosen value's shape differ
    per domain (documented on DecisionResponse below).
    """
    BETTING = auto()       # fold/check/call/bet/raise, with sizing
    CARD_SELECT = auto()   # choose N cards from a single zone (discard, draw)
    CARD_PASS = auto()     # choose N cards from a zone to send to a target
    BOOLEAN = auto()        # yes/no (e.g. Grinch's "Christmas next street?")
    CHOICE = auto()          # pick one label from an enumerated option set


# ---------------------------------------------------------------------
# Card zones
# ---------------------------------------------------------------------

class CardZone(Enum):
    """
    A logical location cards can occupy. CardMove and the CARD_SELECT /
    CARD_PASS decision domains describe themselves purely in terms of
    these zones plus a resolved index -- never anything variant-specific.
    """
    DECK = auto()
    DISCARD_PILE = auto()
    HAND = auto()         # requires a player_index
    BOARD_NODE = auto()   # requires a node_index (a single node_cards slot)


@dataclass(frozen=True)
class ZoneRef:
    """A concrete pointer into a CardZone, e.g. HAND of player 2."""

    zone: CardZone
    index: Optional[int] = None  # player_index for HAND, node_index for BOARD_NODE

    def __post_init__(self):
        if self.zone in (CardZone.HAND, CardZone.BOARD_NODE) and self.index is None:
            raise ValueError(f"{self.zone.name} requires an index")

    def __repr__(self):
        if self.index is None:
            return self.zone.name
        return f"{self.zone.name}[{self.index}]"


# ---------------------------------------------------------------------
# Per-domain option payloads
#
# These describe *legal* choices, not the choice itself. They're what a
# DecisionRequest.options entry looks like for each domain.
# ---------------------------------------------------------------------

@dataclass(frozen=True)
class BettingOption:
    """One legal betting action. min_amount == max_amount for
    fixed-size actions (fold/check/call); a real range for bet/raise."""

    action_type: ActionType
    min_amount: int = 0
    max_amount: int = 0


@dataclass(frozen=True)
class CardSelectOption:
    """
    Legal CARD_SELECT decision: choose between min_count and max_count
    cards from `source`.

    If replace_from_deck is False, chosen cards are simply removed from
    `source` (-> discard pile) -- e.g. a plain Discard mechanic.
    If True, an equal number of replacement cards are then dealt from
    the deck back into `source` -- e.g. Draw.
    """

    source: ZoneRef
    min_count: int
    max_count: int
    replace_from_deck: bool = False


@dataclass(frozen=True)
class CardPassOption:
    """
    Legal CARD_PASS decision: choose exactly `count` cards from `source`
    to send to `target`.

    `target` is already resolved by the variant's targeting rule (e.g.
    "pass to the player on my left") before the decision is ever offered
    -- the player only ever chooses *which cards*, never *who to pass
    to*. A future domain can add recipient choice explicitly if some
    variant ever needs it; CARD_PASS deliberately does not conflate the
    two.
    """

    source: ZoneRef
    target: ZoneRef
    count: int


@dataclass(frozen=True)
class BooleanOption:
    """A yes/no decision. `label` is descriptive only (e.g. "trigger_christmas"),
    used for UI/AI context and for recording which flag the answer sets."""

    label: str = "confirm"


@dataclass(frozen=True)
class ChoiceOption:
    """Pick exactly one label from an enumerated set."""

    labels: Tuple[str, ...]


DecisionOption = Union[
    BettingOption, CardSelectOption, CardPassOption, BooleanOption, ChoiceOption
]


# ---------------------------------------------------------------------
# The unified request / response envelope
# ---------------------------------------------------------------------

@dataclass(frozen=True)
class DecisionRequest:
    """
    Everything a decision-maker (human UI or AI) needs to resolve the
    decision on offer at the current graph node. This is the only thing
    an AI model needs to understand to play any variant: it never sees
    node types, phases, or variant names -- only "it's my turn, domain X,
    here are my legal options."
    """

    node_id: str
    domain: DecisionDomain
    player_index: int
    options: Tuple[DecisionOption, ...]

    # Free-form, node/variant-specific context that never changes option
    # legality but may help a UI/AI render or reason about the decision,
    # e.g. {"reason": "grinch"} on a BOOLEAN node, or {"street": "turn"}.
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DecisionResponse:
    """
    What the decision-maker sends back. `value`'s shape depends on domain:

      BETTING      -> Action                  (poker_engine.actions.action.Action)
      CARD_SELECT  -> Tuple[int, ...]          (card ids chosen from source)
      CARD_PASS    -> Tuple[int, ...]          (card ids chosen from source)
      BOOLEAN      -> bool
      CHOICE       -> str                      (must be one of ChoiceOption.labels)

    node_id/domain/player_index must echo the DecisionRequest being
    answered; the engine validates the response against the *current*
    legal DecisionRequest before applying it (never trusts a stale one).
    """

    node_id: str
    domain: DecisionDomain
    player_index: int
    value: Any