"""
poker_engine/graph/decision_dto.py

decision_request_to_dict(request: DecisionRequest) -> dict

Serializes a DecisionRequest (core_types.py) into a plain JSON-ready
dict for the API layer. This is the graph-engine analogue of
app/engine_adapter.py's state_to_dto() -- but for the *decision on
offer*, not the whole table state. It does not yet exist anywhere in
the backend; game_service.py is still built entirely on PokerState /
GameStateDTO (see CAP_Technical_Document.md §3.5). This module is
scoped to be dropped in once that migration happens, and to be the one
place option-shape knowledge lives, so a frontend consumer never needs
to know DecisionOption is a tagged union of 5 dataclasses.

Per-domain option shape emitted (all fields are the option's OWN
top-level fields -- there is no nested "metadata" dict on any
DecisionOption subclass; core_types.py defines min_count/max_count
directly on CardSelectOption, count directly on CardPassOption, etc.):

  BETTING:
    {"action_type": "FOLD"|"CHECK"|"CALL"|"BET"|"RAISE",
     "min_amount": int, "max_amount": int}

  CARD_SELECT:
    {"source": "<ZoneRef repr>", "min_count": int, "max_count": int,
     "replace_from_deck": bool}
    -- min_count/max_count are what a frontend needs to know how many
    cards to let the player select; read straight off the option, no
    unwrapping required.

  CARD_PASS:
    {"source": "<ZoneRef repr>", "target": "<ZoneRef repr>", "count": int}

  BOOLEAN:
    {"label": str}

  CHOICE:
    {"labels": [str, ...]}

`node_id`, `domain`, `player_index`, and `context` are carried through
unchanged from the DecisionRequest itself.
"""

from typing import Any, Dict

from poker_engine.graph.core_types import (
    BettingOption,
    BooleanOption,
    CardPassOption,
    CardSelectOption,
    ChoiceOption,
    DecisionOption,
    DecisionRequest,
)


def _option_to_dict(option: DecisionOption) -> Dict[str, Any]:
    if isinstance(option, BettingOption):
        return {
            "action_type": option.action_type.name,
            "min_amount": option.min_amount,
            "max_amount": option.max_amount,
        }

    if isinstance(option, CardSelectOption):
        return {
            "source": repr(option.source),
            "min_count": option.min_count,
            "max_count": option.max_count,
            "replace_from_deck": option.replace_from_deck,
        }

    if isinstance(option, CardPassOption):
        return {
            "source": repr(option.source),
            "target": repr(option.target),
            "count": option.count,
        }

    if isinstance(option, BooleanOption):
        return {"label": option.label}

    if isinstance(option, ChoiceOption):
        return {"labels": list(option.labels)}

    raise TypeError(f"No DTO mapping for option type {type(option).__name__}")


def decision_request_to_dict(request: DecisionRequest) -> Dict[str, Any]:
    return {
        "node_id": request.node_id,
        "domain": request.domain.name,
        "player_index": request.player_index,
        "options": [_option_to_dict(o) for o in request.options],
        "context": dict(request.context),
    }