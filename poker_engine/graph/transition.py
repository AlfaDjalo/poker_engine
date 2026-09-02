"""
poker_engine/graph/transition.py

A directed edge between two graph nodes, guarded by a Condition.

Transitions out of a given node are evaluated in listed order; the first
whose condition evaluates True is taken. A node's transition list should
end with an Always()-guarded transition (or have none, for terminal
nodes) so flow is always well-defined -- GameGraph's validator (see
game_graph.py) checks this and raises at load time rather than letting a
hand silently deadlock mid-play.
"""

from dataclasses import dataclass

from poker_engine.graph.condition import Condition


@dataclass(frozen=True)
class Transition:
    from_node: str
    to_node: str
    condition: Condition

    def __repr__(self):
        return f"{self.from_node} -> {self.to_node} [{self.condition!r}]"