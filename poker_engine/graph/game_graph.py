"""
poker_engine/graph/game_graph.py

GameGraph: an immutable, validated container of Nodes + Transitions that
GraphEngine walks.

This is deliberately dumb. GameGraph has no execution logic of its own --
it doesn't know what an AUTO handler does, doesn't evaluate Conditions,
doesn't touch GameState. It only answers three questions GraphEngine
asks on every step:

  - graph.node(node_id)        -> the Node at this id
  - graph.outgoing(node_id)    -> that node's Transitions, in the order
                                   they should be tried
  - graph.is_terminal(node_id) -> True if the hand ends here (no
                                   outgoing transitions were ever defined)

A game variant's entire flow -- every node, every transition, every
condition -- is expressed by constructing a GameGraph once at variant-
definition time (see loader.py, once it's updated to build one of these
instead of a GameDefinition's street list). GraphGameState only ever
stores current_node: str; GameGraph is what turns that string into
"what happens next."

---------------------------------------------------------------------
Validation, and why it happens once at build() rather than per-step
---------------------------------------------------------------------

GraphEngine's own `_advance_transition` (see graph_engine.py) assumes
every non-terminal node's outgoing transition list ends with a match
that is guaranteed to fire -- i.e. an unconditional (Always()) guard, or
more generally "the last transition never fails to match" -- and treats
hitting the end of that list without a match as an engine-invariant
violation (GraphEngineError), not a user-input error. That invariant is
exactly what GameGraph.build() checks, once, at load time -- so a badly
authored variant graph fails loudly when it's defined, not silently
mid-hand three streets into a live game.

A node with NO outgoing transitions at all is not an error -- it's how
a terminal node (hand complete) is expressed. See is_terminal().

Two nodes are never allowed to share an id (nodes is keyed by id), and
every transition's from_node/to_node must reference a real node --
typos become a build()-time ValueError instead of a runtime KeyError
buried inside GraphEngine.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple

from poker_engine.graph.condition import Always
from poker_engine.graph.node import Node
from poker_engine.graph.transition import Transition


class GameGraphError(ValueError):
    """Raised for structural problems found while building a GameGraph
    (unknown node references, missing entry node, a non-terminal node
    whose transitions aren't guaranteed to resolve, ...). Subclasses
    ValueError -- these are configuration/authoring mistakes in a
    variant definition, not engine-internal invariant violations
    (contrast GraphEngineError in graph_engine.py, which is reserved for
    "this should be unreachable if GameGraph.build() already validated
    the graph")."""


@dataclass(frozen=True)
class GameGraph:
    """
    Immutable game-flow graph for one variant.

    Construct via GameGraph.build(...) rather than the constructor
    directly -- build() runs validation the plain constructor doesn't
    (dataclass field defaults alone can't enforce cross-referential
    invariants like "every transition.from_node exists").
    """

    entry_node: str
    nodes: Dict[str, Node] = field(default_factory=dict)
    # Keyed by from_node, values are that node's outgoing Transitions in
    # the exact order they should be tried (see Transition's own
    # docstring: first matching Condition wins).
    _outgoing: Dict[str, Tuple[Transition, ...]] = field(default_factory=dict)

    # -----------------------------------------------------
    # Construction
    # -----------------------------------------------------

    @classmethod
    def build(
        cls,
        nodes: Sequence[Node],
        transitions: Sequence[Transition],
        entry_node: str,
    ) -> "GameGraph":
        """
        Validate and assemble a GameGraph.

        Raises GameGraphError for any of:
          - duplicate node ids
          - entry_node not present in `nodes`
          - a transition referencing an unknown from_node/to_node
          - a non-terminal node (i.e. one with >=1 outgoing transition)
            whose LAST outgoing transition is not unconditionally
            guaranteed to match (either an explicit Always(), or -- for
            any Condition subclass that can't be inspected structurally
            -- the caller is responsible for making the true fallback
            last; Always() is the recommended/expected way to do this
            and is what's checked for here)
        """
        node_by_id: Dict[str, Node] = {}
        for n in nodes:
            if n.id in node_by_id:
                raise GameGraphError(f"Duplicate node id: {n.id!r}")
            node_by_id[n.id] = n

        if entry_node not in node_by_id:
            raise GameGraphError(f"entry_node {entry_node!r} is not a defined node")

        outgoing: Dict[str, List[Transition]] = {}
        for t in transitions:
            if t.from_node not in node_by_id:
                raise GameGraphError(
                    f"Transition {t!r} has unknown from_node {t.from_node!r}"
                )
            if t.to_node not in node_by_id:
                raise GameGraphError(
                    f"Transition {t!r} has unknown to_node {t.to_node!r}"
                )
            outgoing.setdefault(t.from_node, []).append(t)

        for node_id, ts in outgoing.items():
            last = ts[-1]
            if not isinstance(last.condition, Always):
                raise GameGraphError(
                    f"Node {node_id!r}: last outgoing transition must be "
                    f"unconditionally guarded (Always()) so flow is always "
                    f"well-defined, got {last.condition!r} on {last!r}"
                )

        frozen_outgoing = {k: tuple(v) for k, v in outgoing.items()}

        return cls(entry_node=entry_node, nodes=node_by_id, _outgoing=frozen_outgoing)

    # -----------------------------------------------------
    # Queries -- the only surface GraphEngine touches
    # -----------------------------------------------------

    def node(self, node_id: str) -> Node:
        try:
            return self.nodes[node_id]
        except KeyError:
            raise GameGraphError(f"Unknown node id: {node_id!r}") from None

    def outgoing(self, node_id: str) -> Tuple[Transition, ...]:
        """Outgoing transitions for `node_id`, in try-order. Empty for a
        terminal node."""
        return self._outgoing.get(node_id, ())

    def is_terminal(self, node_id: str) -> bool:
        """A node is terminal iff no outgoing transitions were ever
        defined for it -- e.g. a HAND_COMPLETE node reached after
        showdown/award_last_player, with nowhere left to go."""
        return node_id not in self._outgoing or len(self._outgoing[node_id]) == 0

    # -----------------------------------------------------

    def __repr__(self):
        return f"GameGraph(entry={self.entry_node!r}, nodes={len(self.nodes)})"