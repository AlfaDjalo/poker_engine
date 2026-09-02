"""
poker_engine/graph/node.py

Graph node definitions.

A Node is either:

  - AUTO: the engine performs it without any player decision -- dealing
    cards per a fixed list of CardMoves, posting blinds/antes, resolving
    a showdown, paying out a pot, or a no-op setup/completion marker.
    `auto_type` names which built-in handler runs (see graph_engine.py's
    AUTO_HANDLERS registry).

  - DECISION: exactly one player must resolve a Decision (see
    core_types.py) before the graph can proceed. This covers betting AND
    every hand-move choice (discard, draw, pass, boolean, choice)
    identically -- only `domain` and `decision_config` differ between,
    say, a betting round and a discard round. There is no separate
    "betting node" type; BETTING is just one DecisionDomain among others.

Nodes intentionally know nothing about "streets". Where street identity
is useful for display/logging or a legacy sizing rule (e.g.
FixedLimitRules' small-bet/big-bet split), it's carried as an OPTIONAL
metadata["street_index"] entry -- never a structural requirement of the
graph itself.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, Optional, Tuple

from poker_engine.graph.core_types import DecisionDomain
from poker_engine.graph.card_move import CardMove


class NodeKind(Enum):
    AUTO = auto()
    DECISION = auto()


@dataclass(frozen=True)
class Node:
    id: str
    kind: NodeKind

    # ---- AUTO-node config ----
    auto_type: Optional[str] = None
    card_moves: Tuple[CardMove, ...] = ()  # used by auto_type == "deal"

    # ---- DECISION-node config ----
    domain: Optional[DecisionDomain] = None
    # Resolves WHO must act: a fixed role name ("current_player", "dealer",
    # "last_aggressor") resolved the same way condition.CurrentPlayerIs
    # resolves roles, or a DecisionFlag-style key set by an earlier
    # decision (e.g. "pass_target" recorded by a targeting rule). Kept as
    # a plain string here rather than importing Condition machinery into
    # Node, since role resolution belongs to GraphEngine/GameState, not
    # to the node definition itself.
    decider: Optional[str] = None

    # Generic per-node configuration, consumed by whatever handles this
    # node: for a DECISION node, the matching resolver in
    # decision_domains/*.py (e.g. for CARD_SELECT:
    #   {"source": ZoneRef(HAND, player), "min_count": 0, "max_count": 5,
    #    "replace_from_deck": True});
    # for an AUTO node whose handler needs parameters beyond card_moves
    # (e.g. "post_blinds" needs {"small_blind": 1, "big_blind": 2}).
    # A single generic dict rather than two separately-named ones, since
    # both are "config this node's handler reads" and splitting them by
    # node kind would just mean every AUTO handler needing a parameter
    # has to check two places.
    config: Dict[str, Any] = field(default_factory=dict)

    label: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.kind == NodeKind.AUTO and self.auto_type is None:
            raise ValueError(f"AUTO node {self.id!r} requires auto_type")
        if self.kind == NodeKind.DECISION and (self.domain is None or self.decider is None):
            raise ValueError(f"DECISION node {self.id!r} requires domain and decider")