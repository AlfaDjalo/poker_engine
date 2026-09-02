"""
poker_engine/graph/graph_skeleton.py

GraphSkeleton: a mutable Node/Transition accumulator with a
.build() -> GameGraph step. Used by flow_loader.py while compiling a
variant's `flow:` YAML, and available for any custom
{name}_graph.py (see loader.py's _resolve_custom_graph_builder) that
needs to hand-assemble a graph the declarative flow schema can't
express.
"""

from dataclasses import dataclass, field
from typing import Dict, List

from poker_engine.graph.game_graph import GameGraph
from poker_engine.graph.node import Node
from poker_engine.graph.transition import Transition


@dataclass
class GraphSkeleton:
    entry_node: str
    nodes: List[Node] = field(default_factory=list)
    transitions: List[Transition] = field(default_factory=list)
    stage_ids: Dict[str, str] = field(default_factory=dict)

    def retarget(self, from_node: str, old_to_node: str, new_to_node: str) -> None:
        """Repoint every from_node -> old_to_node transition to instead
        go from_node -> new_to_node. Raises if none match (almost always
        means a stage id was mistyped)."""
        matched = False
        for i, t in enumerate(self.transitions):
            if t.from_node == from_node and t.to_node == old_to_node:
                self.transitions[i] = Transition(from_node, new_to_node, t.condition)
                matched = True
        if not matched:
            raise ValueError(f"retarget(): no transition {from_node!r} -> {old_to_node!r} found")

    def build(self) -> GameGraph:
        return GameGraph.build(self.nodes, self.transitions, self.entry_node)