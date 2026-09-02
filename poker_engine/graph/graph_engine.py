"""
poker_engine/graph/graph_engine.py

GraphEngine: the generic executor for a GameGraph.

Replaces PokerState's fixed Phase enum / step() state machine. Instead of
a hardcoded HAND_START -> BETTING -> DEAL_BOARD -> ... loop, GraphEngine
just walks whatever graph it's given:

  - AUTO nodes run automatically (their auto_type handler mutates state),
    then the engine evaluates that node's outgoing Transitions and moves
    on -- repeatedly, with no pause, until it either hits a DECISION node
    or a terminal node.
  - DECISION nodes pause execution: the engine asks that domain's
    DecisionDomainResolver (see decision_domains/) to build a
    DecisionRequest and hands it back to the caller (human UI or AI).
    Nothing advances until submit_decision() is called with a matching
    DecisionResponse.

This is deliberately domain-agnostic at the core-loop level: the loop
itself has no knowledge of "betting" vs "discarding" vs anything else --
it only knows AUTO vs DECISION, and dispatches by table lookup
(AUTO_HANDLERS, and DecisionDomainResolver's registry). That's what makes
this the single orchestration path for every variant, human play, AI
play, and replay: an AI just needs to answer whatever DecisionRequest
comes back, the same way for a bet as for a discard.

AUTO_HANDLERS is the small, closed set of primitives every variant's
graph is built from:

  deal                  execute a fixed list of node.card_moves (board
                         dealing -- node indices are the same regardless
                         of player count, so this can be static config)
  deal_hole_cards        deal node.config["count"] cards, round-robin, to
                         node.config["eligible"] players (dynamic -- the
                         set of eligible players depends on the actual
                         table, so this can't be a static card_moves list
                         the way board dealing can). Also how ESG/
                         Christmas bonus cards are dealt -- same
                         primitive, just reached via a conditional
                         transition instead of always.
  post_blinds            post small/big blind from node.config
  post_antes              post ante from node.config
  reset_betting_round      GameState.reset_betting_round() -- placed once
                           per street, immediately before that street's
                           first BET decision node
  begin_decision_round      GraphGameState.begin_round() -- the non-
                             betting-round equivalent, placed once before
                             a CARD_SELECT/CARD_PASS/etc. round's first
                             decision node
  set_first_to_act          scan for the first eligible player starting
                             node.config["offset"] seats after the
                             dealer (offset=3 for standard preflop,
                             offset=1 for postflop)
  showdown                   resolve the hand via engine.showdown_resolver
                              (already applies payouts internally)
  award_last_player           award the pot to the sole remaining
                               (non-folded) player, no card evaluation
  distribute_passes            apply every pending CARD_PASS decision
                                recorded at node.config["decision_node"]
                                simultaneously (see decision_domains/card_pass.py)
  noop                          does nothing -- a pure branch/marker node

A project needing a primitive not on this list adds ONE function and
registers it in AUTO_HANDLERS; nothing else here changes.
"""

from typing import Any, Dict, List, Optional

from poker_engine.graph.card_move import CardMove, CardMoveExecutor
from poker_engine.graph.condition import ConditionContext
from poker_engine.graph.core_types import CardZone, DecisionResponse, ZoneRef
from poker_engine.graph.decision_domains.base import get_resolver
import poker_engine.graph.decision_domains  # noqa: F401 -- side effect: registers built-in resolvers
from poker_engine.graph.decision_domains.card_pass import execute_pending_passes
from poker_engine.graph.game_graph import GameGraph
from poker_engine.graph.graph_state import GraphGameState
from poker_engine.graph.node import Node, NodeKind


class GraphEngineError(Exception):
    """Raised for engine-level invariant violations (never user-input errors --
    those raise ValueError from validate(), matching DecisionDomainResolver)."""


class GraphEngine:

    def __init__(self, graph: GameGraph, state: GraphGameState, deck, showdown_resolver=None):
        self.graph = graph
        self.state = state
        self.deck = deck
        self.showdown_resolver = showdown_resolver  # poker_engine.showdown.showdown_resolver.ShowdownResolver

        # Set by showdown/award_last_player AUTO handlers, mirroring
        # PokerState.last_showdown/last_winners for anything downstream
        # (UI, logging, RL) that already expects those two attributes.
        self.last_showdown = None
        self.last_winners: Optional[List[int]] = None

        self._pending_request = None
        self._extra: Dict[str, Any] = {}

    # -----------------------------------------------------
    # Public API
    # -----------------------------------------------------

    @property
    def pending_request(self):
        """The DecisionRequest currently awaiting a response, or None if
        the hand is between decisions (shouldn't happen once start()/
        submit_decision() return) or complete."""
        return self._pending_request

    @property
    def is_complete(self) -> bool:
        return self.state.current_node is not None and self.graph.is_terminal(self.state.current_node)

    def start(self) -> None:
        """Enter the graph at its entry node and run until the first
        DECISION node or a terminal node (a graph with no decisions at
        all -- unusual, but not invalid -- completes immediately)."""
        self.state.current_node = self.graph.entry_node
        self._run()

    def submit_decision(self, response: DecisionResponse) -> None:
        """
        Resolve the currently-pending DecisionRequest with `response`,
        then run forward until the next DECISION node or terminal node.
        Raises if there's no pending request, or if `response` doesn't
        match it (stale node_id) or isn't legal (delegated to the
        domain resolver's own validate(), via apply()).
        """
        if self._pending_request is None:
            raise GraphEngineError("submit_decision() called with no decision pending")
        if response.node_id != self._pending_request.node_id:
            raise ValueError(
                f"Response node_id {response.node_id!r} does not match "
                f"pending request {self._pending_request.node_id!r}"
            )

        node = self.graph.node(self.state.current_node)
        resolver = get_resolver(node.domain)
        extra = resolver.apply(node, self.state, self.deck, response)  # re-validates internally

        self._pending_request = None
        self._extra = extra or {}
        self._advance_transition(node.id)
        self._run()

    # -----------------------------------------------------
    # Core loop
    # -----------------------------------------------------

    def _run(self) -> None:
        """Process AUTO nodes until hitting a DECISION node or a terminal node."""
        while True:
            node_id = self.state.current_node

            if self.graph.is_terminal(node_id):
                self._pending_request = None
                return

            node = self.graph.node(node_id)

            if node.kind == NodeKind.DECISION:
                resolver = get_resolver(node.domain)
                self._pending_request = resolver.build_request(node, self.state, self.deck)
                return

            handler = AUTO_HANDLERS.get(node.auto_type)
            if handler is None:
                raise GraphEngineError(f"No AUTO handler registered for auto_type {node.auto_type!r}")

            self._extra = {}
            extra = handler(self, node)
            if extra:
                self._extra.update(extra)

            self._advance_transition(node.id)

    def _advance_transition(self, from_node_id: str) -> None:
        ctx = ConditionContext(state=self.state, deck=self.deck, extra=self._extra)
        for t in self.graph.outgoing(from_node_id):
            if t.condition.evaluate(ctx):
                self.state.current_node = t.to_node
                return
        # Unreachable for a graph built via GameGraph.build(), whose
        # validator guarantees the last outgoing transition of every
        # non-terminal node is unconditional.
        raise GraphEngineError(
            f"No transition out of {from_node_id!r} matched -- "
            f"this indicates the graph was not built via GameGraph.build()"
        )


# =======================================================================
# AUTO node handlers
#
# Each handler has signature (engine: GraphEngine, node: Node) -> Optional[dict].
# The optional returned dict becomes ConditionContext.extra for evaluating
# THIS node's own outgoing transitions (see condition.py's ExtraValue) --
# unused by any handler below today, but kept as a hook rather than
# something bolted on later, since a future mechanic may need it.
# =======================================================================

def _eligible_for_deal(kind: str, state) -> List[int]:
    if kind == "has_stack":
        return [i for i, p in enumerate(state.players) if p.stack > 0]
    if kind == "active":
        return state.active_players()
    if kind == "remaining":
        return state.remaining_players()
    if kind == "all":
        return list(range(len(state.players)))
    raise ValueError(f"Unknown eligible kind for dealing: {kind!r}")


def handle_deal(engine: "GraphEngine", node: Node) -> None:
    executor = CardMoveExecutor()
    for move in node.card_moves:
        executor.execute(move, engine.state, engine.deck)


def handle_deal_hole_cards(engine: "GraphEngine", node: Node) -> None:
    count = node.config["count"]
    eligible = _eligible_for_deal(node.config.get("eligible", "has_stack"), engine.state)
    executor = CardMoveExecutor()
    for _ in range(count):
        for p in eligible:
            move = CardMove(
                source=ZoneRef(CardZone.DECK),
                destination=ZoneRef(CardZone.HAND, p),
                count=1,
            )
            executor.execute(move, engine.state, engine.deck)


def _post_forced_bet(state, index: int, amount: int, track_current_bet: bool) -> None:
    player = state.players[index]
    posted = min(amount, player.stack)
    player.stack -= posted
    if track_current_bet:
        player.current_bet += posted
    player.total_contribution += posted
    state.pot += posted
    if player.stack == 0:
        player.is_all_in = True


def handle_post_blinds(engine: "GraphEngine", node: Node) -> None:
    state = engine.state
    n = len(state.players)
    small_blind = node.config["small_blind"]
    big_blind = node.config["big_blind"]

    sb_idx = (state.dealer_position + 1) % n
    bb_idx = (state.dealer_position + 2) % n
    _post_forced_bet(state, sb_idx, small_blind, track_current_bet=True)
    _post_forced_bet(state, bb_idx, big_blind, track_current_bet=True)

    state.bet_to_call = big_blind
    state.min_raise = big_blind


def handle_post_antes(engine: "GraphEngine", node: Node) -> None:
    # NOTE: faithfully replicates a pre-existing quirk from PokerState.
    # _post_antes/_post_blind (see the original poker_state.py): ante
    # amounts are added to player.current_bet, not just total_contribution.
    # Since bet_to_call is set to big_blind (not big_blind + ante) by
    # handle_post_blinds, this effectively discounts the preflop call
    # for non-blind players by the ante amount -- almost certainly an
    # existing bug, but out of scope for this port to fix silently.
    # Flagging it here rather than "fixing" it invisibly.
    state = engine.state
    amount = node.config["ante"]
    for i in range(len(state.players)):
        _post_forced_bet(state, i, amount, track_current_bet=True)


def handle_reset_betting_round(engine: "GraphEngine", node: Node) -> None:
    engine.state.reset_betting_round()


def handle_begin_decision_round(engine: "GraphEngine", node: Node) -> None:
    engine.state.begin_round()


def handle_set_first_to_act(engine: "GraphEngine", node: Node) -> None:
    """
    Sets both state.current_player and state.last_to_act.

    last_to_act uses the same active-list method as
    GameState.reset_betting_round() (active players in ascending seat
    order; last_to_act is the active player immediately before
    current_player in that cyclic order) rather than a naive
    (current_player - 1) % n -- the naive formula is only correct when
    nobody has folded yet, and silently breaks the very first time it
    isn't (last_to_act can end up pointing at a folded player who can
    never legitimately act again, so the "turn has cycled back" check
    that drives BettingRoundComplete never fires). The active-list
    method is a strict generalization: with nobody folded it reduces to
    exactly the naive formula, so there's no reason to keep both.
    """
    state = engine.state
    n = len(state.players)
    offset = node.config.get("offset", 1)
    for i in range(n):
        idx = (state.dealer_position + offset + i) % n
        p = state.players[idx]
        if not p.has_folded and not p.is_all_in:
            state.current_player = idx
            active = state.active_players()
            state.last_to_act = active[active.index(idx) - 1]
            return
    # No eligible player: leave current_player/last_to_act unchanged. A
    # graph should route away from any node that needs one (via a
    # PlayersRemainingCount()<=1 -style condition) before ever reaching
    # this handler in that situation -- see award_last_player.


def handle_showdown(engine: "GraphEngine", node: Node) -> None:
    if engine.showdown_resolver is None:
        raise GraphEngineError(
            "GraphEngine has no showdown_resolver configured; cannot reach a 'showdown' AUTO node"
        )
    result = engine.showdown_resolver.resolve(engine.state)
    engine.last_showdown = result
    engine.last_winners = [p for p, amt in result.payouts.items() if amt > 0]
    engine.state.pot = 0


def handle_award_last_player(engine: "GraphEngine", node: Node) -> None:
    state = engine.state
    for i, p in enumerate(state.players):
        if not p.has_folded:
            p.stack += state.pot
            engine.last_showdown = None
            engine.last_winners = [i]
            state.pot = 0
            return
    raise GraphEngineError("award_last_player reached with no remaining (non-folded) players")


def handle_distribute_passes(engine: "GraphEngine", node: Node) -> None:
    decision_node = node.config["decision_node"]
    execute_pending_passes(decision_node, engine.state, engine.deck)


def handle_noop(engine: "GraphEngine", node: Node) -> None:
    return None


AUTO_HANDLERS = {
    "deal": handle_deal,
    "deal_hole_cards": handle_deal_hole_cards,
    "post_blinds": handle_post_blinds,
    "post_antes": handle_post_antes,
    "reset_betting_round": handle_reset_betting_round,
    "begin_decision_round": handle_begin_decision_round,
    "set_first_to_act": handle_set_first_to_act,
    "showdown": handle_showdown,
    "award_last_player": handle_award_last_player,
    "distribute_passes": handle_distribute_passes,
    "noop": handle_noop,
}