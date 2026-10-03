"""
poker_engine/graph/graph_hole_cards.py

hole_cards_per_player(graph): the single, correct way to answer "how many
hole cards does each player start the hand with" for a graph-native
GameDefinition/GameGraph.

Why this exists
----------------
GameDefinition deliberately no longer carries a `hole_cards` field for the
graph-native loader (poker_engine.rules.graph_loader.load_game_graph()) --
see game_definition.py's docstring and CAP_Technical_Quick_Reference.md
§12.4. That count is flow-step config now, not a static per-variant fact
(a variant can deal MORE hole cards mid-hand via ESG/Christmas/Grinch --
see extra_cards.py -- so a single static int wouldn't even be the right
shape for "how many hole cards will this player ever hold").

Two independent Backend call sites (game_service._summarize_flow,
equity_service._hole_cards_per_player_from_metadata) each guessed that a
compiled Node's `.metadata` dict carries a `deals_hole: true` / `card_count`
key. It doesn't, anywhere -- flow_loader.py copies a flow step's
`metadata:` block through UNCHANGED (see that module's Pass 1), and no
variant YAML ever puts `deals_hole`/`card_count` under `metadata:` (every
`deal_hole_cards` step's count lives in `config: {count: N, ...}` instead
-- see holdem.yaml/plo8.yaml/drawmaha.yaml/etc.). That's why the
metadata walk finds nothing for Hold'em (or any other variant) and falls
through to equity_service's dry-run-and-count fallback.

The actual, load-bearing signal is structural, on Node itself:
  - node.kind == NodeKind.AUTO
  - node.auto_type == "deal_hole_cards"
  - node.config["count"]   (read directly by
    graph_engine.handle_deal_hole_cards -- this IS what the engine itself
    trusts, so it's the only thing safe to trust here too)

This module walks graph.nodes once and sums config["count"] across every
"deal_hole_cards" node reachable in the graph -- covering both the
ordinary single preflop deal AND any variant whose flow deals hole cards
again later via a second "deal_hole_cards" step (not
"deal_extra_hole_card", which is the ESG/Christmas/Grinch bonus-card
primitive and is intentionally excluded -- see extra_cards.py; those are
conditional/per-hand, not a fixed starting count, and equity/config
summaries that want "starting hole cards" should not count them).
"""

from typing import Optional

from poker_engine.graph.game_graph import GameGraph
from poker_engine.graph.node import NodeKind


def hole_cards_per_player(graph: GameGraph) -> int:
    """
    Sum of node.config["count"] across every AUTO node in `graph` whose
    auto_type == "deal_hole_cards". This is the number of hole cards
    every dealt-in player starts the hand with.

    Does NOT include deal_extra_hole_card (ESG/Catchup ESG/Christmas/
    Grinch) nodes -- those are conditional bonus cards, not part of the
    fixed starting count. A caller that specifically needs "max possible
    hole cards this hand could reach" is a different question this
    function doesn't answer.

    Raises ValueError if no deal_hole_cards node exists at all -- every
    real variant has exactly one; a graph with none is almost certainly
    a construction bug, not a legitimate zero-hole-card game.
    """
    total = 0
    found = False

    for node in graph.nodes.values():
        if node.kind == NodeKind.AUTO and node.auto_type == "deal_hole_cards":
            found = True
            total += node.config["count"]

    if not found:
        raise ValueError(
            "hole_cards_per_player: graph has no 'deal_hole_cards' AUTO "
            "node -- cannot determine starting hole card count"
        )

    return total


def first_deal_hole_cards_count(graph: GameGraph) -> Optional[int]:
    """
    Convenience variant: just the count on the FIRST deal_hole_cards node
    encountered (graph.nodes iteration order == insertion order, i.e. the
    order flow_loader.py emitted them in, which for every current variant
    is exactly one node, the preflop deal). Returns None rather than
    raising if absent, for call sites that want a soft fallback instead
    of a hard error (e.g. a config-summary endpoint that would rather
    omit the field than 500).
    """
    for node in graph.nodes.values():
        if node.kind == NodeKind.AUTO and node.auto_type == "deal_hole_cards":
            return node.config["count"]
    return None