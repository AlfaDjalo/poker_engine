"""
poker_engine/graph/flow_loader.py

build_flow_graph(flow_spec, award_last_player_next): compile a
variant's declarative `flow:` YAML list directly into a GameGraph.

This supersedes standard_graph.py's earlier procedural builder. That
approach INFERRED graph structure from board_layout/betting config --
two representations of the same thing (config -> code -> graph), which
is exactly the indirection the original graph-model brief argued
against. Here the YAML *is* the graph: every node in the resulting
GameGraph corresponds to exactly one `flow` entry (or, for the one
compound step type -- see below -- a small, fixed, fully-documented
expansion of one entry into a couple of internal nodes).

Step types map 1:1 onto the existing generic vocabulary:
  - Any AUTO auto_type already in graph_engine.py's AUTO_HANDLERS
    (noop, deal_hole_cards, post_blinds, post_antes,
    reset_betting_round, set_first_to_act, showdown, award_last_player,
    begin_decision_round, distribute_passes) is usable directly as a
    step `type`, with `config`/`metadata` passed straight through to
    the Node.
  - `type: deal` is sugar for an AUTO "deal" node: `board_nodes: [...]`
    expands to one CardMove (DECK -> BOARD_NODE[n]) per index, since
    hand-writing CardMove tuples in YAML would be pure noise for the
    overwhelmingly common case of "deal these board slots".
  - `type: card_select` / `card_pass` / `boolean` / `choice` map
    directly onto the matching DecisionDomain, `decider` and `config`
    passed straight through. These are single-node steps -- unlike
    `betting` (below), no round-completion sugar is built for them yet,
    so a variant using CARD_SELECT/CARD_PASS as a multi-player round
    needs to author begin_decision_round + the decision node + its own
    RoundComplete-guarded self-loop explicitly via `transitions:`. This
    is a deliberate, documented scope limit (see
    poker_engine/graph/standard_graph.py's own equivalent note on
    FixedLimitRules/river_only): additive whenever a variant actually
    needs it, not built speculatively.
  - `type: betting` IS a compound step -- the one exception. It expands
    to [reset_betting_round? ->] set_first_to_act -> a BETTING decision
    node with a self-loop (round incomplete), a branch to the reserved
    `award_last_player` node (round complete, <=1 player remains), and
    a forward branch to the next step. This mirrors exactly what
    standard_graph.py used to build procedurally, but as a fixed,
    documented expansion of ONE declarative step -- not inferred from
    separate board/betting config sections. "betting" is one of the
    primitives the graph-model brief itself names as first-class
    (alongside dealing/showdown/payout), so a dedicated compound step
    for it is the intended shape, not a special case.

Default sequencing: consecutive steps chain via an unconditional
Always() transition from one step to the next, UNLESS the step is
`type: betting` (which wires its own branches, see above), is marked
`terminal: true` (no outgoing edges at all), or supplies its own
`transitions: [{to: ..., when: ...}, ...]` list (see
yaml_conditions.py for the `when` grammar) -- which REPLACES the
default chain entirely, for variants that need real branching (a
future Grinch/Christmas-style BOOLEAN decision, for instance).

`to:` in an explicit transition (and the built-in award_last_player
target) refers to a step's declared `id`, resolved through this
module's internal id->entry-node lookup -- so branching to a `betting`
step by its id correctly lands on that step's actual entry node (its
reset/first-to-act prelude), not on the DECISION node itself.
"""

from typing import Dict, List, Optional

from poker_engine.betting.betting_rules import AllInOrFoldRules, BettingRules, FixedLimitRules, NoLimitRules, PotLimitRules
from poker_engine.graph.card_move import CardMove
from poker_engine.graph.condition import ActivePlayersCount, Always, And, BettingRoundComplete, Compare, Not, PlayersRemainingCount
from poker_engine.graph.core_types import CardZone, DecisionDomain, ZoneRef
from poker_engine.graph.node import Node, NodeKind
from poker_engine.graph.graph_skeleton import GraphSkeleton
from poker_engine.graph.transition import Transition
from poker_engine.graph.yaml_conditions import parse_condition

AWARD_LAST_PLAYER_ID = "award_last_player"

_STANDARD_AUTO_TYPES = {
    "noop",
    "deal_hole_cards",
    "deal_extra_hole_card",
    "post_blinds",
    "post_antes",
    "reset_betting_round",
    "set_first_to_act",
    "showdown",
    "award_last_player",
    "begin_decision_round",
    "distribute_passes",
}

_DECISION_DOMAINS = {
    "card_select": DecisionDomain.CARD_SELECT,
    "card_pass": DecisionDomain.CARD_PASS,
    "boolean": DecisionDomain.BOOLEAN,
    "choice": DecisionDomain.CHOICE,
}


def _build_betting_rules(spec: dict) -> BettingRules:
    kind = spec["kind"]
    if kind == "no_limit":
        return NoLimitRules()
    if kind == "pot_limit":
        return PotLimitRules()
    if kind == "push_fold":
        return AllInOrFoldRules()
    if kind == "fixed_limit":
        return FixedLimitRules(
            small_bet=spec["small_bet"],
            big_bet=spec["big_bet"],
            raise_cap=spec.get("raise_cap", 4),
        )
    raise ValueError(f"Unknown betting rules kind: {kind!r}")


def _board_card_moves(board_nodes: List[int]):
    return tuple(
        CardMove(source=ZoneRef(CardZone.DECK), destination=ZoneRef(CardZone.BOARD_NODE, n), count=1)
        for n in board_nodes
    )


def build_flow_graph(flow_spec: List[dict], award_last_player_next: Optional[str] = None) -> GraphSkeleton:
    if not flow_spec:
        raise ValueError("flow: must contain at least one step")

    step_ids = [s["id"] for s in flow_spec]
    if len(step_ids) != len(set(step_ids)):
        raise ValueError("flow: step ids must be unique")
    id_index = {sid: i for i, sid in enumerate(step_ids)}

    needs_award = any(s.get("type") == "betting" for s in flow_spec)
    if needs_award:
        if not award_last_player_next:
            raise ValueError(
                "flow: contains a 'betting' step, so top-level "
                "'award_last_player_next: <step id>' is required (where "
                "to route to when everyone but one player has folded)"
            )
        if award_last_player_next not in id_index:
            raise ValueError(
                f"award_last_player_next {award_last_player_next!r} is not a flow step id"
            )

    skeleton = GraphSkeleton(entry_node=step_ids[0])
    entry: Dict[str, str] = {}  # step id -> the actual first graph-node id for that step

    # ---- Pass 1: create every Node, compute `entry[step_id]` ----
    for step in flow_spec:
        sid = step["id"]
        stype = step.get("type")
        if stype is None:
            raise ValueError(f"flow step {sid!r} is missing 'type'")
        metadata = step.get("metadata", {})
        config = step.get("config", {})

        if stype == "betting":
            local = []
            if step.get("reset", True):
                reset_id = f"{sid}__reset"
                skeleton.nodes.append(Node(id=reset_id, kind=NodeKind.AUTO, auto_type="reset_betting_round"))
                local.append(reset_id)
            fta_id = f"{sid}__first_to_act"
            skeleton.nodes.append(
                Node(
                    id=fta_id,
                    kind=NodeKind.AUTO,
                    auto_type="set_first_to_act",
                    config={"offset": step.get("first_to_act_offset", 1)},
                )
            )
            local.append(fta_id)
            for a, b in zip(local, local[1:]):
                skeleton.transitions.append(Transition(a, b, Always()))
            entry[sid] = local[0]

            rules = _build_betting_rules(step["rules"])
            skeleton.nodes.append(
                Node(
                    id=sid,
                    kind=NodeKind.DECISION,
                    domain=DecisionDomain.BETTING,
                    decider=step.get("decider", "current_player"),
                    config={"rules": rules},
                    metadata=metadata,
                )
            )

        elif stype == "deal":
            card_moves = _board_card_moves(step.get("board_nodes", []))
            skeleton.nodes.append(
                Node(id=sid, kind=NodeKind.AUTO, auto_type="deal", card_moves=card_moves, metadata=metadata)
            )
            entry[sid] = sid

        elif stype in _STANDARD_AUTO_TYPES:
            skeleton.nodes.append(Node(id=sid, kind=NodeKind.AUTO, auto_type=stype, config=config, metadata=metadata))
            entry[sid] = sid

        elif stype in _DECISION_DOMAINS:
            skeleton.nodes.append(
                Node(
                    id=sid,
                    kind=NodeKind.DECISION,
                    domain=_DECISION_DOMAINS[stype],
                    decider=step.get("decider", "current_player"),
                    config=config,
                    metadata=metadata,
                )
            )
            entry[sid] = sid

        else:
            raise ValueError(f"flow step {sid!r}: unknown type {stype!r}")

    if needs_award:
        skeleton.nodes.append(Node(id=AWARD_LAST_PLAYER_ID, kind=NodeKind.AUTO, auto_type="award_last_player"))
        entry[AWARD_LAST_PLAYER_ID] = AWARD_LAST_PLAYER_ID
        skeleton.transitions.append(
            Transition(AWARD_LAST_PLAYER_ID, entry[award_last_player_next], Always())
        )

    skeleton.stage_ids = dict(entry)

    # ---- Pass 2: wire cross-step edges (entry[] is now fully known) ----
    for i, step in enumerate(flow_spec):
        sid = step["id"]
        stype = step["type"]
        terminal = step.get("terminal", False)
        next_step_id = step_ids[i + 1] if i + 1 < len(step_ids) else None
        next_entry = entry[next_step_id] if next_step_id else None

        if stype == "betting":
            fta_id = f"{sid}__first_to_act"
            if next_entry is None:
                raise ValueError(f"betting step {sid!r} cannot be the last flow step")

            # first_to_act: nobody can act this round (all remaining
            # players are folded/all-in) -> award if <=1 remain overall,
            # else skip straight past betting to whatever's next.
            skeleton.transitions.append(
                Transition(
                    fta_id,
                    AWARD_LAST_PLAYER_ID,
                    And(Compare(ActivePlayersCount(), "==", 0), Compare(PlayersRemainingCount(), "<=", 1)),
                )
            )
            skeleton.transitions.append(
                Transition(fta_id, next_entry, Compare(ActivePlayersCount(), "==", 0))
            )
            skeleton.transitions.append(Transition(fta_id, sid, Always()))

            # bet node: loop while incomplete, else award or move on.
            skeleton.transitions.append(Transition(sid, sid, Not(BettingRoundComplete())))
            skeleton.transitions.append(
                Transition(
                    sid,
                    AWARD_LAST_PLAYER_ID,
                    And(BettingRoundComplete(), Compare(PlayersRemainingCount(), "<=", 1)),
                )
            )
            skeleton.transitions.append(Transition(sid, next_entry, Always()))
            continue

        if "transitions" in step:
            for t in step["transitions"]:
                to_id = entry.get(t["to"], t["to"])
                skeleton.transitions.append(Transition(sid, to_id, parse_condition(t.get("when"))))
            continue

        if terminal:
            continue

        if next_entry is None:
            raise ValueError(
                f"flow step {sid!r} has no explicit 'transitions' and is the last "
                f"step, but isn't marked terminal: true -- either add "
                f"'terminal: true' or an explicit transitions list"
            )
        skeleton.transitions.append(Transition(sid, next_entry, Always()))

    return skeleton