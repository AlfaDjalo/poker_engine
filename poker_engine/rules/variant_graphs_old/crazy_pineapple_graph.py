"""
poker_engine/rules/variant_graphs/crazy_pineapple_graph.py

build_graph(raw_yaml) for crazy_pineapple.yaml. Identical shape to
pineapple_graph.py -- only where the discard round is spliced in
differs (after bet_flop instead of after bet_preflop).
"""

from poker_engine.graph.flow_loader import build_flow_graph
from poker_engine.graph.graph_skeleton import GraphSkeleton
from poker_engine.rules.variant_graphs._discard_round import splice_discard_round


def build_graph(raw_yaml: dict) -> GraphSkeleton:
    skeleton = build_flow_graph(
        raw_yaml["flow"],
        award_last_player_next=raw_yaml.get("award_last_player_next"),
    )

    splice_discard_round(
        skeleton,
        round_id="discard_flop",
        after_stage_id="bet_flop",
        before_stage_id="deal_turn",
        config={"min_count": 1, "max_count": 1, "replace_from_deck": False},
    )

    return skeleton