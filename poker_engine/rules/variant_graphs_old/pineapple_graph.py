"""
poker_engine/rules/variant_graphs/pineapple_graph.py

build_graph(raw_yaml) for pineapple.yaml -- see that file's own comment
on why this exists instead of a plain `flow:` load, and
_discard_round.py's docstring for why the discard round can't be
expressed as YAML `transitions:`.
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
        round_id="discard_preflop",
        after_stage_id="bet_preflop",
        before_stage_id="deal_flop",
        config={"min_count": 1, "max_count": 1, "replace_from_deck": False},
    )

    return skeleton