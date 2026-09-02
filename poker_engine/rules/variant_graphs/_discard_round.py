"""
poker_engine/rules/variant_graphs/_discard_round.py

splice_discard_round(...): insert a CARD_SELECT discard round into a
GraphSkeleton that was otherwise built declaratively via
flow_loader.build_flow_graph().

Why this can't just be a `transitions:` block in the variant's own YAML
--------------------------------------------------------------------
Per flow_loader.py's own docstring, a CARD_SELECT round needs a
begin_decision_round AUTO node + the CARD_SELECT DECISION node + a
hand-authored RoundComplete-guarded self-loop, wired via the step's own
`transitions:` list. That's exactly what yaml_conditions.py's grammar
looks like it supports (`{round_complete: <value spec>}`) -- but
condition.RoundComplete's `eligible` argument must be an Accessor that
resolves to a *list* of player indices (ActivePlayers() /
RemainingPlayers()), and yaml_conditions.py's `_ACCESSORS` table only
ever maps YAML `accessor:` keys to Accessors that resolve to *counts*
(ActivePlayersCount, PlayersRemainingCount, ...) or scalars
(DecisionFlag/ExtraValue/Constant). There is no YAML-reachable accessor
that returns the player-index list RoundComplete actually needs, so
`{round_complete: {accessor: active_players_count}}` would build without
error but crash the first time RoundComplete.evaluate() tries to
`for p in eligible_players` over an int.

Until yaml_conditions.py grows an `active_players` / `remaining_players`
list accessor, any variant needing a CARD_SELECT/CARD_PASS round has to
splice it in from a custom {name}_graph.py using the real Python
Accessor classes directly -- which is what this module does, once,
so every such variant doesn't reimplement the same splice.

FIRST-TO-ACT (added -- was previously missing entirely)
--------------------------------------------------------------------
The round used to go straight from begin_decision_round (which only
resets state.round_acted) into the CARD_SELECT node itself, with
NOTHING establishing a starting current_player for the round. That
left current_player at whatever the PRECEDING step (almost always a
betting round) happened to leave it at -- which is frequently NOT a
player eligible for this round: e.g. the betting action closed on a
player who went all-in to call, so current_player is that now-all-in
player, excluded from eligible="active". CardSelectResolver's own
_current_actor() then raised "current_player is not eligible" the
instant the round tried to build its very first DecisionRequest --
surfacing as an unexplained 400 on exactly the action that closed
betting and should have opened the discard round, and ONLY on hands
where the closing action happened to leave current_player ineligible
(hence intermittent, not every hand).

Fixed by inserting a `set_first_to_act` AUTO node (the SAME handler
betting steps already use -- see flow_loader.py/graph_engine.py; its
"not folded, not all-in" scan matches eligible="active" exactly)
between begin_decision_round and the CARD_SELECT node, so the round
always starts on a genuinely eligible seat regardless of what the
preceding step left behind.

Usage
-----
Write the variant's `flow:` as if the discard round weren't there (i.e.
the step immediately before the round transitions straight to the step
immediately after it), build it normally via build_flow_graph(), then
call this to cut the round in between:

    skeleton = build_flow_graph(raw_yaml["flow"], raw_yaml.get("award_last_player_next"))
    splice_discard_round(
        skeleton,
        round_id="discard_flop",
        after_stage_id="bet_flop",     # the flow step id whose Always()
                                        # transition should now go through
                                        # the discard round first
        before_stage_id="deal_turn",   # the flow step id that used to be
                                        # the direct target
        config={"min_count": 1, "max_count": 1, "replace_from_deck": False},
    )
    return skeleton
"""

from poker_engine.graph.condition import ActivePlayers, Always, Not, RemainingPlayers, RoundComplete
from poker_engine.graph.core_types import DecisionDomain
from poker_engine.graph.graph_skeleton import GraphSkeleton
from poker_engine.graph.node import Node, NodeKind
from poker_engine.graph.transition import Transition


def splice_discard_round(
    skeleton: GraphSkeleton,
    round_id: str,
    after_stage_id: str,
    before_stage_id: str,
    config: dict,
    eligible: str = "active",
    first_to_act_offset: int = 1,
) -> None:
    """
    Insert `after_stage_id --Always()--> [begin_decision_round ->
    set_first_to_act -> CARD_SELECT (self-loop until RoundComplete)
    --Always()--> before_stage_id's entry]` into `skeleton`, replacing
    the direct `after_stage_id -> before_stage_id` edge that
    build_flow_graph() already wired.

    `after_stage_id` must be the literal id of the step whose own Always()
    edge should be redirected -- for a `betting` step this is the step's
    declared `id:` (the DECISION node itself is what the placeholder
    "next street" edge actually originates from; see flow_loader.py's
    Pass 2), not its `__reset`/`__first_to_act` prelude.

    `before_stage_id` is looked up through skeleton.stage_ids, exactly
    like flow_loader.py's own `entry[...]` resolution -- so retargeting
    into a `betting` step correctly lands on that step's reset/
    first-to-act prelude, not its DECISION node.

    `eligible`: "active" (not folded, not all-in -- matches
    GameState.advance_turn()'s own skip rule, the normal choice) or
    "remaining" (not folded, including all-in -- see CardSelectResolver's
    own note on this not yet being sufficient alone, since
    advance_turn() doesn't visit all-in players either).

    `first_to_act_offset`: seats after the dealer to start scanning for
    the round's first actor -- same convention postflop betting steps
    already default to (first_to_act_offset: 1). See module docstring's
    "FIRST-TO-ACT" section for why this matters -- without it the round
    inherited an arbitrary, frequently-ineligible current_player from
    whatever step preceded it.

    Raises KeyError if `before_stage_id` isn't a known stage, and
    ValueError (via GraphSkeleton.retarget) if `after_stage_id` has no
    existing edge into `before_stage_id`'s entry -- both almost always
    mean a stage id was mistyped.
    """
    begin_id = f"{round_id}__begin"
    fta_id = f"{round_id}__first_to_act"
    before_entry = skeleton.stage_ids[before_stage_id]

    skeleton.nodes.append(Node(id=begin_id, kind=NodeKind.AUTO, auto_type="begin_decision_round"))
    skeleton.nodes.append(
        Node(
            id=fta_id,
            kind=NodeKind.AUTO,
            auto_type="set_first_to_act",
            config={"offset": first_to_act_offset},
        )
    )
    skeleton.nodes.append(
        Node(
            id=round_id,
            kind=NodeKind.DECISION,
            domain=DecisionDomain.CARD_SELECT,
            decider="current_player",
            config=dict(config, eligible=eligible),
        )
    )
    skeleton.stage_ids[round_id] = begin_id

    skeleton.retarget(after_stage_id, before_entry, begin_id)
    skeleton.transitions.append(Transition(begin_id, fta_id, Always()))
    skeleton.transitions.append(Transition(fta_id, round_id, Always()))

    eligible_accessor = ActivePlayers() if eligible == "active" else RemainingPlayers()
    skeleton.transitions.append(Transition(round_id, round_id, Not(RoundComplete(eligible_accessor))))
    skeleton.transitions.append(Transition(round_id, before_entry, Always()))