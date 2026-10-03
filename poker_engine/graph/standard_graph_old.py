"""
poker_engine/graph/standard_graph.py

build_standard_graph(game_def): constructs the GameGraph for the ordinary
"deal hole cards, post forced bets, then [deal board street / betting
round] repeated per street, then showdown" flow shared by Hold'em, PLO8,
Drawmaha, and bomb-pot variants like double_board_plo_bomb_pot.

This is NOT a special Hold'em code path. It's a generic assembler that
reads the same GameDefinition fields loader.py already parses from a
variant's YAML (hole_cards, street_nodes, betting_type, blinds, ante) and
emits an ordinary GameGraph out of the same primitives every other graph
uses (deal, deal_hole_cards, post_blinds, post_antes,
reset_betting_round, set_first_to_act, a BETTING decision node,
showdown, award_last_player). Hold'em is simply the variant whose
GameDefinition happens to produce the simplest instance of this shape
(street 0 empty -> no deal_board before the first betting round).

A variant that needs something this shape can't express -- ESG,
Christmas, Grinch, Pass the Trash, Draw, Discard, or any other mid-hand
event -- does NOT extend or parameterize this builder further. It
constructs its OWN list of Node/Transition (by hand, or by splicing
extra nodes into the output of this builder -- see "Splicing" below) and
calls GameGraph.build() directly. Keeping this builder narrowly scoped
to "the boring, common case" is deliberate: the moment it grows
variant-specific flags, it becomes exactly the kind of "graph as a
collection of special-case poker rules" the architecture is trying to
avoid.

---------------------------------------------------------------------
Splicing
---------------------------------------------------------------------

`build_standard_graph` returns a GraphSkeleton, not just a GameGraph --
the intermediate `nodes`/`transitions` lists plus a `stage_ids` map are
exposed specifically so a variant author can lift a whole street's worth
of already-correct dealing/betting nodes and re-target a handful of
transitions (e.g. insert a CARD_SELECT discard round between
`bet_1` and `deal_board_2` by redirecting `bet_1`'s Always() transition
at a new node instead of `deal_board_2`, and pointing that new node back
at `deal_board_2` once the discard round completes) rather than
reimplementing the whole street sequence by hand. GraphSkeleton.build()
just calls GameGraph.build() on the accumulated lists; call it once
splicing is done.

---------------------------------------------------------------------
Known simplifications
---------------------------------------------------------------------

- Betting-type support is currently NoLimitRules / PotLimitRules /
  AllInOrFoldRules (push_fold). FixedLimitRules needs a small_bet/big_bet
  split that GameDefinition doesn't carry yet, and "river_only" has no
  BettingRules subclass at all yet (see betting.py's own docstring note
  on that same gap) -- both raise NotImplementedError here rather than
  silently doing the wrong thing.
- Every betting round in a variant uses the SAME BettingRules instance
  (one per graph, built once from game_def.betting_type). A variant
  that genuinely needs FixedLimitRules pre-flop/flop and NoLimitRules
  later (see betting.py's docstring on this) isn't expressible through
  this builder and should assemble its BET nodes by hand instead.
"""

from dataclasses import dataclass, field
from typing import Dict, List

from poker_engine.betting.betting_rules import AllInOrFoldRules, BettingRules, NoLimitRules, PotLimitRules
from poker_engine.graph.card_move import CardMove
from poker_engine.graph.condition import (
    ActivePlayersCount,
    Always,
    And,
    BettingRoundComplete,
    Compare,
    Not,
    PlayersRemainingCount,
)
from poker_engine.graph.core_types import CardZone, DecisionDomain, ZoneRef
from poker_engine.graph.game_graph import GameGraph
from poker_engine.graph.node import Node, NodeKind
from poker_engine.graph.transition import Transition

AWARD_LAST_PLAYER_ID = "award_last_player"
COMPLETE_ID = "complete"


@dataclass
class GraphSkeleton:
    """
    Mutable accumulator of Nodes/Transitions plus a name->id map for the
    stages build_standard_graph() laid down (e.g. stage_ids["bet_1"],
    stage_ids["deal_board_2"]) so a caller can splice additional nodes
    into the flow before finalizing. See module docstring, "Splicing".
    """

    entry_node: str
    nodes: List[Node] = field(default_factory=list)
    transitions: List[Transition] = field(default_factory=list)
    stage_ids: Dict[str, str] = field(default_factory=dict)

    def retarget(self, from_node: str, old_to_node: str, new_to_node: str) -> None:
        """
        Repoint every Transition currently going from_node -> old_to_node
        so it instead goes from_node -> new_to_node. The standard splice
        operation: "whatever used to come after old_to_node should now
        come after new_to_node instead". Raises if no such transition
        exists, since a silent no-op almost always means a stage id was
        mistyped.
        """
        matched = False
        for i, t in enumerate(self.transitions):
            if t.from_node == from_node and t.to_node == old_to_node:
                self.transitions[i] = Transition(from_node, new_to_node, t.condition)
                matched = True
        if not matched:
            raise ValueError(
                f"retarget(): no transition {from_node!r} -> {old_to_node!r} found"
            )

    def build(self) -> GameGraph:
        return GameGraph.build(self.nodes, self.transitions, self.entry_node)


def _betting_rules_for(game_def) -> BettingRules:
    bt = game_def.betting_type
    if bt == "no_limit":
        return NoLimitRules()
    if bt == "pot_limit":
        return PotLimitRules()
    if bt == "push_fold":
        return AllInOrFoldRules()
    raise NotImplementedError(
        f"build_standard_graph: no BettingRules mapping for betting_type "
        f"{bt!r}. FixedLimitRules needs a small_bet/big_bet split that "
        f"GameDefinition doesn't carry, and 'river_only' has no "
        f"BettingRules subclass yet (see betting.py's own docstring). "
        f"Assemble this variant's BET nodes by hand instead of using "
        f"build_standard_graph()."
    )


def build_standard_graph(game_def) -> GraphSkeleton:
    """
    Assemble the standard deal/bet/deal/bet.../showdown GameGraph for
    `game_def` (a poker_engine.rules.game_definition.GameDefinition).

    Returns a GraphSkeleton -- call .build() on it to get the finished,
    validated GameGraph, or splice in extra nodes first (see module
    docstring).
    """
    rules = _betting_rules_for(game_def)

    skeleton = GraphSkeleton(entry_node="setup")

    # ---------------------------------------------------------
    # Fixed opening sequence: setup -> deal_hole -> [antes] -> [blinds]
    # ---------------------------------------------------------

    skeleton.nodes.append(Node(id="setup", kind=NodeKind.AUTO, auto_type="noop"))
    skeleton.stage_ids["setup"] = "setup"

    skeleton.nodes.append(
        Node(
            id="deal_hole",
            kind=NodeKind.AUTO,
            auto_type="deal_hole_cards",
            config={"count": game_def.hole_cards, "eligible": "has_stack"},
        )
    )
    skeleton.stage_ids["deal_hole"] = "deal_hole"
    skeleton.transitions.append(Transition("setup", "deal_hole", Always()))

    tail = "deal_hole"

    if game_def.ante > 0:
        skeleton.nodes.append(
            Node(id="post_antes", kind=NodeKind.AUTO, auto_type="post_antes", config={"ante": game_def.ante})
        )
        skeleton.stage_ids["post_antes"] = "post_antes"
        skeleton.transitions.append(Transition(tail, "post_antes", Always()))
        tail = "post_antes"

    if game_def.small_blind > 0 or game_def.big_blind > 0:
        skeleton.nodes.append(
            Node(
                id="post_blinds",
                kind=NodeKind.AUTO,
                auto_type="post_blinds",
                config={"small_blind": game_def.small_blind, "big_blind": game_def.big_blind},
            )
        )
        skeleton.stage_ids["post_blinds"] = "post_blinds"
        skeleton.transitions.append(Transition(tail, "post_blinds", Always()))
        tail = "post_blinds"

    # ---------------------------------------------------------
    # One segment per street: [deal_board_i if that street has board
    # cards] -> [reset_betting_round_i if i > 0] -> first_to_act_i ->
    # bet_i (self-looping until the round completes).
    #
    # Street 0 never resets the betting round and always uses the
    # preflop first-actor offset (dealer + 3), regardless of whether
    # street 0 itself deals board cards (a bomb pot's simultaneous
    # flops) -- this mirrors PokerState.start_hand()/_first_to_act_
    # preflop(), which apply the same rule unconditionally. Streets
    # after the first always reset and use the postflop offset
    # (dealer + 1), matching PokerState.step()'s DEAL_BOARD handling.
    # ---------------------------------------------------------

    num_streets = len(game_def.street_nodes)

    for i, board_nodes in enumerate(game_def.street_nodes):

        street_name = (
            game_def.street_names[i] if i < len(game_def.street_names) else f"street_{i}"
        )

        # This street's own internal chain -- deal_board? -> reset? ->
        # first_to_act -- wired with plain Always() edges among nodes
        # created in THIS iteration only. The edge INTO the first node
        # of that chain (street_entry_id, below) is wired separately:
        # directly from the opening sequence's `tail` when i == 0, or
        # (for i > 0) deferred to the "__AFTER_STREET__" placeholder
        # resolution below -- never both, which was the bug this
        # comment replaces: appending `Transition(tail, deal_id, ...)`
        # unconditionally here double-wired every deal_board_i (i > 0)
        # node, since `tail` at the top of iteration i is always the
        # PREVIOUS street's bet_id, whose own placeholder transition
        # already resolves to exactly this same deal_id.
        local_chain: List[str] = []

        if board_nodes:
            deal_id = f"deal_board_{i}"
            card_moves = tuple(
                CardMove(
                    source=ZoneRef(CardZone.DECK),
                    destination=ZoneRef(CardZone.BOARD_NODE, n),
                    count=1,
                )
                for n in board_nodes
            )
            skeleton.nodes.append(
                Node(
                    id=deal_id,
                    kind=NodeKind.AUTO,
                    auto_type="deal",
                    card_moves=card_moves,
                    metadata={"street_index": i, "street_name": street_name},
                )
            )
            skeleton.stage_ids[deal_id] = deal_id
            local_chain.append(deal_id)

        if i > 0:
            reset_id = f"reset_betting_round_{i}"
            skeleton.nodes.append(Node(id=reset_id, kind=NodeKind.AUTO, auto_type="reset_betting_round"))
            skeleton.stage_ids[reset_id] = reset_id
            local_chain.append(reset_id)

        first_to_act_id = f"first_to_act_{i}"
        bet_id = f"bet_{i}"
        offset = 3 if i == 0 else 1

        skeleton.nodes.append(
            Node(
                id=first_to_act_id,
                kind=NodeKind.AUTO,
                auto_type="set_first_to_act",
                config={"offset": offset},
            )
        )
        skeleton.stage_ids[first_to_act_id] = first_to_act_id
        local_chain.append(first_to_act_id)

        # Wire this street's internal chain (deal_board? -> reset? ->
        # first_to_act), then wire the edge INTO the chain: directly
        # from the opening sequence for street 0, or left for the
        # "__AFTER_STREET__" placeholder resolution (below) to wire
        # from the previous street's bet_id/first_to_act_id otherwise.
        for a, b in zip(local_chain, local_chain[1:]):
            skeleton.transitions.append(Transition(a, b, Always()))

        street_entry_id = local_chain[0]
        if i == 0:
            skeleton.transitions.append(Transition(tail, street_entry_id, Always()))

        # Determine what comes after this street's betting -- the next
        # stage in sequence, or showdown if this was the last street.
        # Resolved as a placeholder here; wired to the real next id once
        # the loop reaches it, via the deferred-transition pass below.
        after_betting_placeholder = ("__AFTER_STREET__", i)

        skeleton.nodes.append(
            Node(
                id=bet_id,
                kind=NodeKind.DECISION,
                domain=DecisionDomain.BETTING,
                decider="current_player",
                config={"rules": rules},
                metadata={"street_index": i, "street_name": street_name},
            )
        )
        skeleton.stage_ids[bet_id] = bet_id

        # first_to_act_i: nobody can act this round (everyone remaining
        # is folded/all-in) -> either award (<=1 player left at all) or
        # skip straight past betting to whatever comes after this street.
        skeleton.transitions.append(
            Transition(
                first_to_act_id,
                AWARD_LAST_PLAYER_ID,
                And(Compare(ActivePlayersCount(), "==", 0), Compare(PlayersRemainingCount(), "<=", 1)),
            )
        )
        skeleton.transitions.append(
            Transition(first_to_act_id, after_betting_placeholder, Compare(ActivePlayersCount(), "==", 0))
        )
        skeleton.transitions.append(Transition(first_to_act_id, bet_id, Always()))

        # bet_i: keep looping while the round isn't complete; once
        # complete, award if only one player remains, else move on.
        skeleton.transitions.append(Transition(bet_id, bet_id, Not(BettingRoundComplete())))
        skeleton.transitions.append(
            Transition(
                bet_id,
                AWARD_LAST_PLAYER_ID,
                And(BettingRoundComplete(), Compare(PlayersRemainingCount(), "<=", 1)),
            )
        )
        skeleton.transitions.append(Transition(bet_id, after_betting_placeholder, Always()))

    # `tail` is no longer read after this point -- every street i > 0 is
    # entered exclusively via the "__AFTER_STREET__" placeholder
    # resolution below, never via `tail`.

    # ---------------------------------------------------------
    # Showdown / completion
    # ---------------------------------------------------------

    skeleton.nodes.append(Node(id="showdown", kind=NodeKind.AUTO, auto_type="showdown"))
    skeleton.stage_ids["showdown"] = "showdown"
    skeleton.transitions.append(Transition("showdown", COMPLETE_ID, Always()))

    skeleton.nodes.append(
        Node(id=AWARD_LAST_PLAYER_ID, kind=NodeKind.AUTO, auto_type="award_last_player")
    )
    skeleton.stage_ids[AWARD_LAST_PLAYER_ID] = AWARD_LAST_PLAYER_ID
    skeleton.transitions.append(Transition(AWARD_LAST_PLAYER_ID, COMPLETE_ID, Always()))

    skeleton.nodes.append(Node(id=COMPLETE_ID, kind=NodeKind.AUTO, auto_type="noop"))
    skeleton.stage_ids[COMPLETE_ID] = COMPLETE_ID
    # COMPLETE_ID has no outgoing transitions -- terminal.

    # ---------------------------------------------------------
    # Resolve the "__AFTER_STREET__" placeholders now that every
    # street's entry id is known: street i's post-betting target is
    # street (i+1)'s first node (deal_board_{i+1}, or
    # reset_betting_round_{i+1}/first_to_act_{i+1} if street i+1 has no
    # board cards), or "showdown" after the last street.
    # ---------------------------------------------------------

    def _street_entry(i: int) -> str:
        if i >= num_streets:
            return "showdown"
        board_nodes = game_def.street_nodes[i]
        if board_nodes:
            return f"deal_board_{i}"
        if i > 0:
            return f"reset_betting_round_{i}"
        return f"first_to_act_{i}"

    resolved = []
    for t in skeleton.transitions:
        if isinstance(t.to_node, tuple) and t.to_node[0] == "__AFTER_STREET__":
            i = t.to_node[1]
            resolved.append(Transition(t.from_node, _street_entry(i + 1), t.condition))
        else:
            resolved.append(t)
    skeleton.transitions = resolved

    return skeleton