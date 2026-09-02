"""
poker_engine/rules/variant_graphs/throw_dem_graph.py

build_graph(raw_yaml) for throw_dem.yaml. Same splice pattern as
pineapple_graph.py/crazy_pineapple_graph.py, applied three times --
once per post-flop street's betting round, per the guide's "discard one
card after each street" rule (see throw_dem.yaml's own comment on the
5 -> 4 -> 3 -> 2 progression).

Order matters: splice_discard_round() retargets an existing edge, so
each call must run before the NEXT edge it will need to retarget has
itself already been retargeted by an earlier call. Since these three
splices touch three disjoint edge pairs (bet_flop->deal_turn,
bet_turn->deal_river, bet_river->showdown), call order here is not
actually load-bearing -- but kept in street order for readability.
"""

from poker_engine.graph.flow_loader import build_flow_graph
from poker_engine.graph.graph_skeleton import GraphSkeleton
from poker_engine.rules.variant_graphs._discard_round import splice_discard_round

_DISCARD_CONFIG = {"min_count": 1, "max_count": 1, "replace_from_deck": False}


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
        config=_DISCARD_CONFIG,
    )
    splice_discard_round(
        skeleton,
        round_id="discard_turn",
        after_stage_id="bet_turn",
        before_stage_id="deal_river",
        config=_DISCARD_CONFIG,
    )
    splice_discard_round(
        skeleton,
        round_id="discard_river",
        after_stage_id="bet_river",
        before_stage_id="showdown",
        config=_DISCARD_CONFIG,
    )

    return skeleton