# poker_engine/games/loader.py
"""
poker_engine/games/loader.py

load_game(name) -> (LegacyGameDefinition, GameRules)

The loader for PokerState (poker_engine/state/poker_state.py). This is
a deliberately separate implementation from
poker_engine.rules.loader.load_game() (the graph-native path
GameService/GraphEngine use, returning a 3-tuple with a GameGraph) --
see CAP_Technical_Quick_Reference.md §4.2/§12.4. PokerState remains the
supported engine for push_fold_service.py / trainer_service.py (RL Lab
integration points whose trained policies' observation-building code
was validated against PokerState's shape); it is not deprecated and
this loader is not a compatibility shim.

Why this parses the YAML independently rather than building on
poker_engine.rules.loader
--------------------------------------------------------------------
The graph-native GameDefinition (poker_engine.rules.game_definition)
does not carry hole_cards/betting_type/small_blind/big_blind/ante/
street_nodes -- those live as flow-step config instead (see that
module's own docstring). PokerState reads every one of those fields
directly (start_hand -> _post_antes -> _post_blinds ->
_deal_hole_cards -> _deal_next_board -> legal_actions/apply_action --
see LegacyGameDefinition's own docstring for the exhaustive list). This
loader derives them by scanning the variant's `flow:` list itself --
the same YAML, read a second, independent way -- with no dependency on
flow_loader.build_flow_graph()/GameGraph. A bug in the graph compiler
can never break push_fold_service.py/trainer_service.py, and vice
versa.

Derivation rules (mirrors what flow_loader.py's compound "betting" step
and "deal" sugar already encode declaratively):

  hole_cards      <- config.count of the flow's (first) deal_hole_cards step
  ante            <- config.ante of the flow's (first) post_antes step (0 if absent)
  small_blind/
  big_blind       <- config of the flow's (first) post_blinds step (0/0 if absent)
  betting_type    <- rules.kind of the flow's FIRST betting step (e.g.
                     "no_limit"/"pot_limit"/"push_fold") -- PokerState's
                     GameState.legal_actions()/apply_action() only
                     special-case "push_fold"/"river_only"/"single_bet";
                     every other kind (no_limit, pot_limit, fixed_limit)
                     falls through the same generic bet/raise branch --
                     legacy GameState was never sized per-street the way
                     BettingRules is; sizing is caller-supplied.
  street_nodes    <- one entry per street_index appearing on a `deal`
                     step's metadata, in ascending order, each holding
                     that step's board_nodes; any index with no `deal`
                     step (Hold'em's street_index 0 -- nothing is dealt
                     before the first, preflop, betting round) is filled
                     in as []. This is exactly what
                     PokerState.start_hand()'s unconditional single
                     _deal_next_board() call at street_nodes[0] expects:
                     [] for a normal preflop start, or real cards for a
                     bomb-pot variant whose first street IS a simultaneous
                     deal (see double_board_plo_bomb_pot.yaml).
  street_names    <- the matching street_name metadata per index,
                     defaulting to f"street_{i}" if absent.

`deal`/`betting` steps tagged street_index: -1 (the documented
non-street sentinel -- ESG/discard/draw/pass-the-trash markers, see
pineapple.yaml/drawmaha.yaml/omaha_esg.yaml etc.) are excluded from
this scan: PokerState has no equivalent concept for them, and neither
push_fold_service.py nor trainer_service.py uses ESG/Christmas/Grinch
variants.

Points/showdown/payout parsing below reads the same YAML
`points:`/`showdown:`/`payout_type:` keys as
poker_engine.rules.loader, independently, so this module has zero
import-time dependency on the graph-native loader or its GameGraph
machinery. That schema is shared and unaffected by which engine loads
it (see CAP §2.1) -- keep the two readings in sync by hand if it ever
changes.
"""

from pathlib import Path
from typing import Tuple

import yaml

from poker_engine.games.legacy_game_definition import LegacyGameDefinition
from poker_engine.rules.game_rules import GameRules, PointDefinition
from poker_engine.poker_eval import ScoreType, ShowdownType

BASE_PATH = Path(__file__).parent.parent / "games"


def load_game(name: str) -> Tuple[LegacyGameDefinition, GameRules]:
    path = BASE_PATH / f"{name}.yaml"
    with open(path) as f:
        data = yaml.safe_load(f)

    rules = _build_rules(data)
    game_def = _build_legacy_game_definition(name, data)

    return game_def, rules


# ---------------------------------------------------------------------
# Points / showdown / payout
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
# LegacyGameDefinition -- derived from `flow:` (see module docstring)
# ---------------------------------------------------------------------

def _build_legacy_game_definition(name: str, data: dict) -> LegacyGameDefinition:
    flow = data.get("flow", [])

    score_types = list({getattr(ScoreType, p["score_type"]) for p in data["points"]})

    game_def = LegacyGameDefinition(
        game_name=name,
        node_count=data["node_count"],
        score_types=score_types,
        layout_name=data.get("layout_name"),
    )

    game_def.hole_cards = _find_hole_cards(flow)
    game_def.ante = _find_ante(flow)
    game_def.small_blind, game_def.big_blind = _find_blinds(flow)
    game_def.betting_type = _find_betting_type(flow)
    game_def.street_nodes, game_def.street_names = _find_streets(flow)

    return game_def


def _find_hole_cards(flow) -> int:
    for step in flow:
        if step.get("type") == "deal_hole_cards":
            return step["config"]["count"]
    raise ValueError(
        "flow: has no 'deal_hole_cards' step -- cannot derive hole_cards "
        "for the legacy GameDefinition"
    )


def _find_ante(flow) -> int:
    for step in flow:
        if step.get("type") == "post_antes":
            return step["config"].get("ante", 0)
    return 0


def _find_blinds(flow) -> Tuple[int, int]:
    for step in flow:
        if step.get("type") == "post_blinds":
            cfg = step["config"]
            return cfg.get("small_blind", 0), cfg.get("big_blind", 0)
    return 0, 0


def _find_betting_type(flow) -> str:
    for step in flow:
        if step.get("type") == "betting":
            return step["rules"]["kind"]
    return "no_limit"


def _find_streets(flow):
    """
    Returns (street_nodes, street_names) -- see module docstring's
    derivation rules. `deal` steps whose metadata.street_index is
    absent or negative (the documented non-street sentinel) are
    skipped entirely; they have no legacy street_nodes equivalent.
    """
    by_index = {}
    names_by_index = {}

    for step in flow:
        if step.get("type") != "deal":
            continue
        metadata = step.get("metadata", {})
        idx = metadata.get("street_index")
        if idx is None or idx < 0:
            continue
        by_index[idx] = step.get("board_nodes", [])
        names_by_index[idx] = metadata.get("street_name", f"street_{idx}")

    if not by_index:
        return [], []

    max_index = max(by_index)
    street_nodes = [by_index.get(i, []) for i in range(max_index + 1)]
    street_names = [names_by_index.get(i, f"street_{i}") for i in range(max_index + 1)]

    return street_nodes, street_names