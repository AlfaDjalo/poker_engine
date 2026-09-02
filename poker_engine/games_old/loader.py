"""
poker_engine/rules/loader.py

load_game(name) -> (GameDefinition, GameRules, GameGraph)

Parses a variant's {name}.yaml. Scoring (points/showdown/payout) is
unchanged from the pre-graph model -- none of that is "flow", and none
of it needed to change. The `flow:` list is compiled into a GameGraph
by flow_loader.build_flow_graph(); see that module for the flow schema
itself.

A variant needing flow that the declarative `flow:` schema can't express
(a genuinely dynamic structure, not just branching -- ordinary branching
is already covered by a step's `transitions:`) may provide
poker_engine/rules/variant_graphs/{name}_graph.py with a
`build_graph(raw_yaml) -> GraphSkeleton` function; load_game() prefers
that over `flow:` if present. This is expected to be rare -- almost
everything, including future ESG/Christmas/Grinch/Pass-the-Trash/Draw/
Discard variants, should be expressible as flow + transitions.
"""

import importlib
from pathlib import Path
from typing import Optional, Tuple

import yaml

from poker_engine.graph.flow_loader import build_flow_graph
from poker_engine.graph.game_graph import GameGraph
from poker_engine.rules.game_definition import GameDefinition
from poker_engine.rules.game_rules import GameRules, PointDefinition
from poker_engine.poker_eval import ScoreType, ShowdownType

BASE_PATH = Path(__file__).parent
_CUSTOM_GRAPH_PACKAGE = "poker_engine.rules.variant_graphs"


def load_game(name: str) -> Tuple[GameDefinition, GameRules, GameGraph]:
    path = BASE_PATH / f"{name}.yaml"
    with open(path) as f:
        data = yaml.safe_load(f)

    # -----------------------------
    # points / scoring (unchanged from the pre-graph model)
    # -----------------------------

    points = []
    score_types = set()

    for p in data["points"]:
        score_type = getattr(ScoreType, p["score_type"])
        score_types.add(score_type)

        override_str = p.get("showdown_type_override")
        showdown_type_override = getattr(ShowdownType, override_str) if override_str else None

        points.append(
            PointDefinition(
                name=p["name"],
                score_type=score_type,
                node_sets=[tuple(ns) for ns in p["node_sets"]],
                showdown_type_override=showdown_type_override,
                scoop_from=p.get("scoop_from"),
            )
        )

    score_types = list(score_types)
    showdown_type = getattr(ShowdownType, data["showdown"]["type"])

    # -----------------------------
    # GameDefinition
    # -----------------------------

    game_def = GameDefinition(
        game_name=name,
        node_count=data["node_count"],
        score_types=score_types,
        layout_name=data.get("layout_name"),
    )

    # -----------------------------
    # GameRules
    # -----------------------------

    rules = GameRules(
        score_types=score_types,
        showdown_type=showdown_type,
        points=points,
        payout_type=data.get("payout_type", "points"),
        low_qualifier=data.get("low_qualifier", 8),
        no_qualify_action=data.get("no_qualify_action", "scoop"),
    )

    # -----------------------------
    # Graph
    # -----------------------------

    custom_builder = _resolve_custom_graph_builder(name)
    if custom_builder is not None:
        skeleton = custom_builder(data)
    else:
        if "flow" not in data:
            raise ValueError(
                f"{name}.yaml has no 'flow:' section and no "
                f"poker_engine/rules/variant_graphs/{name}_graph.py -- "
                f"nothing to build a graph from"
            )
        skeleton = build_flow_graph(data["flow"], award_last_player_next=data.get("award_last_player_next"))

    graph = skeleton.build()

    return game_def, rules, graph


def _resolve_custom_graph_builder(name: str) -> Optional[callable]:
    try:
        module = importlib.import_module(f"{_CUSTOM_GRAPH_PACKAGE}.{name}_graph")
    except ModuleNotFoundError:
        return None
    build_graph = getattr(module, "build_graph", None)
    if build_graph is None:
        raise AttributeError(f"{module.__name__} exists but does not define build_graph(raw_yaml)")
    return build_graph