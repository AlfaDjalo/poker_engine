# poker_engine/rules/loader.py
"""
poker_engine/rules/loader.py

load_game(name) -> (GameDefinition, GameRules, GameGraph)

THE graph-native loader. Every current, non-legacy consumer imports
this as `load_game_graph`:

    from poker_engine.rules.loader import load_game as load_game_graph
    game_def, rules, graph = load_game_graph(game_name)

used by app/services/game_service.py, app/services/equity_service.py,
and app/services/hand_construction_service.py.

This has ZERO dependency on poker_engine.games.loader (the separate,
PokerState-only legacy loader kept alongside for push_fold_service.py /
trainer_service.py until those are ported to GraphEngine -- see
CAP_Technical_Quick_Reference.md §4.2). The two loaders read the same
`points:`/`showdown:`/`payout_type:` YAML keys independently of each
other (see that module's own docstring) -- keep both in sync by hand
if that shared schema ever changes.

GameDefinition, per its own docstring, is deliberately thin: just
game_name/node_count/score_types/layout_name. Everything else a
variant needs (hole card count, betting type, blinds, ante, street
structure) is flow-step config now, expressed once in `flow:` and
compiled straight into the GameGraph by
poker_engine.graph.flow_loader.build_flow_graph() -- never duplicated
onto a dataclass here.

`award_last_player_next` (top-level YAML key, required by
build_flow_graph() whenever the flow contains a `betting` step) is
read straight off `data` and passed through unchanged.
"""

from pathlib import Path
from typing import Tuple

import yaml

from poker_engine.rules.game_definition import GameDefinition
from poker_engine.rules.game_rules import GameRules, PointDefinition
from poker_engine.poker_eval import ScoreType, ShowdownType
from poker_engine.graph.flow_loader import build_flow_graph
from poker_engine.graph.game_graph import GameGraph

BASE_PATH = Path(__file__).parent.parent / "games"


def load_game(name: str) -> Tuple[GameDefinition, GameRules, GameGraph]:
    path = BASE_PATH / f"{name}.yaml"
    with open(path) as f:
        data = yaml.safe_load(f)

    rules = _build_rules(data)
    game_def = _build_game_definition(name, data)
    graph = _build_graph(name, data)

    return game_def, rules, graph


# ---------------------------------------------------------------------
# Points / showdown / payout -- same schema as poker_engine.games.loader,
# read independently (see module docstring).
# ---------------------------------------------------------------------

def _build_rules(data: dict) -> GameRules:
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

    showdown_type = getattr(ShowdownType, data["showdown"]["type"])

    return GameRules(
        score_types=list(score_types),
        showdown_type=showdown_type,
        points=points,
        payout_type=data.get("payout_type", "points"),
        low_qualifier=data.get("low_qualifier", 8),
        no_qualify_action=data.get("no_qualify_action", "scoop"),
    )


# ---------------------------------------------------------------------
# GameDefinition -- thin, graph-native shape (see module docstring)
# ---------------------------------------------------------------------

def _build_game_definition(name: str, data: dict) -> GameDefinition:
    score_types = list({getattr(ScoreType, p["score_type"]) for p in data["points"]})

    return GameDefinition(
        game_name=name,
        node_count=data["node_count"],
        score_types=score_types,
        layout_name=data.get("layout_name"),
    )


# ---------------------------------------------------------------------
# GameGraph -- compiled from `flow:` via flow_loader.build_flow_graph()
# ---------------------------------------------------------------------

def _build_graph(name: str, data: dict) -> GameGraph:
    flow = data.get("flow")
    if not flow:
        raise ValueError(
            f"Variant {name!r} has no 'flow:' list -- cannot build a "
            f"GameGraph. Every graph-native variant must define one "
            f"(see holdem.yaml for the reference shape)."
        )

    skeleton = build_flow_graph(flow, data.get("award_last_player_next"))
    return skeleton.build()