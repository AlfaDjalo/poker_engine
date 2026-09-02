"""
poker_engine/graph/yaml_conditions.py

parse_condition(spec) / parse_value(spec): translate a YAML condition
spec directly into the existing condition.py primitives (Accessor,
Condition, Compare, And/Or/Not, Always, RoundComplete,
BettingRoundComplete). This is NOT a new expression language -- it's a
1:1 YAML surface over condition.py's own deliberately closed grammar
(see that module's docstring). Every keyword here corresponds to one
concrete Python class; there is no operator precedence, no arithmetic,
nothing beyond what a flow YAML author needs to express a branch.

Grammar (a condition spec is one of):
  "always"                                          -> Always()
  {always: true}                                     -> Always()
  {betting_round_complete: true}                     -> BettingRoundComplete()
  {round_complete: <value spec>}                      -> RoundComplete(eligible=<value>)
  {compare: {left: <value>, op: "==", right: <value>}} -> Compare(...)
  {and: [<condition>, ...]}                           -> And(...)
  {or: [<condition>, ...]}                            -> Or(...)
  {not: <condition>}                                  -> Not(...)
  any of the above with `negate: true` alongside it   -> wrapped in Not(...)

A value spec (used inside compare/round_complete) is one of:
  a literal (int / bool / str)                        -> passed through
  {accessor: "active_players_count"}                  -> ActivePlayersCount()
  {accessor: "players_remaining_count"}               -> PlayersRemainingCount()
  {accessor: "active_players"}                        -> ActivePlayers()     (list -- use for round_complete)
  {accessor: "remaining_players"}                     -> RemainingPlayers()  (list -- use for round_complete)
  {accessor: "discard_pile_count"}                    -> DiscardPileCount()
  {accessor: "deck_remaining_count"}                  -> DeckRemainingCount()
  {accessor: "decision_flag", key: "...", default: X} -> DecisionFlag(key, default)
  {accessor: "extra_value", key: "...", default: X}   -> ExtraValue(key, default)
  {constant: X}                                       -> Constant(X)
"""

from poker_engine.graph.condition import (
    ActivePlayers,
    ActivePlayersCount,
    Always,
    And,
    BettingRoundComplete,
    Compare,
    Constant,
    DecisionFlag,
    DeckRemainingCount,
    DiscardPileCount,
    ExtraValue,
    Not,
    Or,
    PlayersRemainingCount,
    RemainingPlayers,
    RoundComplete,
)

_ACCESSORS = {
    "active_players_count": lambda args: ActivePlayersCount(),
    "players_remaining_count": lambda args: PlayersRemainingCount(),
    # List-valued accessors -- required for {round_complete: ...}, which
    # needs an Accessor resolving to a list of player indices (not a
    # count). Previously missing: every YAML round_complete guard would
    # build RoundComplete(<int accessor>) and TypeError at evaluation
    # time the first time a non-betting DECISION round's forward
    # transition was checked (RoundComplete.evaluate() does
    # `for p in eligible_players`, which chokes on an int).
    "active_players": lambda args: ActivePlayers(),
    "remaining_players": lambda args: RemainingPlayers(),
    "discard_pile_count": lambda args: DiscardPileCount(),
    "deck_remaining_count": lambda args: DeckRemainingCount(),
    "decision_flag": lambda args: DecisionFlag(args["key"], args.get("default")),
    "extra_value": lambda args: ExtraValue(args["key"], args.get("default")),
}


def parse_value(spec):
    if isinstance(spec, dict):
        if "accessor" in spec:
            name = spec["accessor"]
            if name not in _ACCESSORS:
                raise ValueError(f"Unknown accessor: {name!r} (known: {sorted(_ACCESSORS)})")
            return _ACCESSORS[name](spec)
        if "constant" in spec:
            return Constant(spec["constant"])
        raise ValueError(f"Unrecognized value spec: {spec!r}")
    return spec  # literal: int / bool / str, compared directly


def parse_condition(spec):
    if spec is None or spec == "always":
        return Always()

    if not isinstance(spec, dict):
        raise ValueError(f"Condition spec must be a mapping or 'always', got {spec!r}")

    if spec.get("always"):
        cond = Always()
    elif spec.get("betting_round_complete"):
        cond = BettingRoundComplete()
    elif "round_complete" in spec:
        cond = RoundComplete(parse_value(spec["round_complete"]))
    elif "compare" in spec:
        c = spec["compare"]
        cond = Compare(parse_value(c["left"]), c["op"], parse_value(c["right"]))
    elif "and" in spec:
        cond = And(*[parse_condition(s) for s in spec["and"]])
    elif "or" in spec:
        cond = Or(*[parse_condition(s) for s in spec["or"]])
    elif "not" in spec:
        cond = Not(parse_condition(spec["not"]))
    else:
        raise ValueError(f"Unrecognized condition spec: {spec!r}")

    if spec.get("negate"):
        cond = Not(cond)
    return cond