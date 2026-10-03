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
  deal_extra_hole_card   ESG / Catchup ESG / Christmas / Grinch bonus
                         cards -- see extra_cards.py.
  post_blinds            post small/big blind from node.config. Also
                         seeds the persistent (cross-street) last-
                         aggressor fallback: posting the BB IS the
                         preflop fallback whenever blinds are in play
                         (see handle_post_blinds below).
  post_antes              post ante from node.config. Seeds the same
                           persistent-aggressor fallback ONLY when this
                           hand has no blinds at all (a bomb pot) -- see
                           handle_post_antes below; handle_post_blinds
                           always wins when both run.
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
                                simultaneously (see decision_domains/card_pass.py).
                                Records what moved onto
                                engine.last_distributed_passes -- see
                                callbacks.py's on_cards_distributed.
  noop                          does nothing -- a pure branch/marker node

A project needing a primitive not on this list adds ONE function and
registers it in AUTO_HANDLERS; nothing else here changes.

---------------------------------------------------------------------
Failure isolation: start()/submit_decision() roll back on exception
---------------------------------------------------------------------

Before either call does anything, it snapshots state+deck+the engine's
own bookkeeping (pending_request, extra, last_showdown, last_winners,
last_distributed_passes). If ANYTHING raises while advancing the graph
(a resolver bug, an AUTO handler bug, a condition evaluation error --
anything), the snapshot is restored onto the SAME state/deck objects
(never rebound, so callers already holding references see the
rollback too) and a GraphEngineStepError is raised, chained from the
original exception.

This means a bug firing mid-advance can never leave the engine wedged
at a half-mutated node with pending_request=None and no way to tell
"a bug just happened" from "there's legitimately nothing pending right
now" (previously both looked identical from the caller's side -- see
GraphEngineStepError's own docstring). The failed call's caller gets a
distinguishable exception type and the SAME pending_request as before
the call, valid to retry (or answer differently) immediately.
"""

import copy
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
from poker_engine.graph.extra_cards import handle_deal_extra_hole_card


class GraphEngineError(Exception):
    """Raised for engine-level invariant violations (never user-input errors --
    those raise ValueError from validate(), matching DecisionDomainResolver)."""


class GraphEngineStepError(GraphEngineError):
    """
    Raised when start()/submit_decision() throws partway through
    advancing the graph (a resolver bug, an AUTO handler bug, anything
    unexpected).

    Unlike a plain exception leaking out of _run(), by the time this is
    raised the engine has ALREADY been rolled back to exactly the state
    it was in before the failed call -- state/deck restored in place,
    pending_request restored to the request that was valid before the
    call. The same decision (or start()) can be safely retried, or a
    different one submitted instead; nothing about the hand was lost.

    This exists specifically so callers (Backend) can distinguish
    "a bug just fired, the engine is fine, retry" (this exception) from
    GraphEngineError("no decision pending") ("this call itself was
    invalid, e.g. hand already complete") -- previously both surfaced
    as the same ambiguous, unrecoverable-looking failure: current_node
    already mutated to the failed node, pending_request permanently
    None, every subsequent call failing the exact same way regardless
    of which player/action was tried next.
    """


def _all_slots(cls) -> List[str]:
    """Every __slots__ name declared anywhere in cls's MRO -- used to
    copy every field of a __slots__-based state/deck object during
    checkpoint/restore without needing a __dict__."""
    slots: List[str] = []
    for klass in cls.__mro__:
        slots.extend(getattr(klass, "__slots__", ()))
    return slots


class GraphEngine:

    def __init__(
        self,
        graph: GameGraph,
        state: GraphGameState,
        deck,
        showdown_resolver=None,
        transactional: bool = True,
    ):
        # transactional=True (default, used by the UI/Backend): every
        # start()/submit_decision() deep-copies state+deck first so a
        # failure rolls the engine back and the call can be retried.
        # transactional=False (RL training): skips those two deepcopies per
        # call -- profiling showed them dominating engine time. A failing
        # step then raises GraphEngineStepError WITHOUT rollback, leaving
        # the engine in an undefined partial state: only safe when a
        # failure means the episode is simply abandoned.
        self.transactional = transactional
        self.graph = graph
        self.state = state
        self.deck = deck
        self.showdown_resolver = showdown_resolver  # poker_engine.showdown.showdown_resolver.ShowdownResolver

        # Set by showdown/award_last_player AUTO handlers, mirroring
        # PokerState.last_showdown/last_winners for anything downstream
        # (UI, logging, RL) that already expects those two attributes.
        self.last_showdown = None
        self.last_winners: Optional[List[int]] = None

        # Set by handle_distribute_passes -- one entry per player whose
        # CARD_PASS was just applied: [{"player", "card_ids", "target"}, ...].
        # None whenever a distribute_passes node has NOT run during the
        # most recent start()/submit_decision() call (reset to None at
        # the top of each) -- so callbacks.py can tell "a distribution
        # happened during THIS call" from a stale leftover from an
        # earlier one. See decision_domains/card_pass.py and
        # callbacks.py's on_cards_distributed.
        self.last_distributed_passes: Optional[List[Dict[str, Any]]] = None

        self._pending_request = None
        self._extra: Dict[str, Any] = {}

    # -----------------------------------------------------
    # Public API
    # -----------------------------------------------------

    @property
    def pending_request(self):
        """The DecisionRequest currently awaiting a response, or None if
        the hand is between decisions (shouldn't happen once start()/
        submit_decision() return normally) or complete."""
        return self._pending_request

    @property
    def is_complete(self) -> bool:
        return self.state.current_node is not None and self.graph.is_terminal(self.state.current_node)

    def start(self) -> None:
        """Enter the graph at its entry node and run until the first
        DECISION node or a terminal node (a graph with no decisions at
        all -- unusual, but not invalid -- completes immediately).

        Rolls back and raises GraphEngineStepError if anything fails
        partway through -- see module docstring."""
        self.last_distributed_passes = None
        checkpoint = self._checkpoint() if self.transactional else None
        try:
            self.state.current_node = self.graph.entry_node
            self._run()
        except Exception as exc:
            if checkpoint is not None:
                self._restore(checkpoint)
            raise GraphEngineStepError(
                f"start() failed while running the graph forward from "
                f"{self.graph.entry_node!r}: {exc!r}. Engine has been "
                f"rolled back; start() may be retried."
            ) from exc

    def submit_decision(self, response: DecisionResponse) -> None:
        """
        Resolve the currently-pending DecisionRequest with `response`,
        then run forward until the next DECISION node or terminal node.
        Raises GraphEngineError if there's no pending request, or
        ValueError if `response` doesn't match it (stale node_id).

        If anything fails while applying the response or advancing the
        graph, the engine is rolled back to exactly its pre-call state
        and GraphEngineStepError is raised -- see module docstring.
        """
        self.last_distributed_passes = None

        if self._pending_request is None:
            raise GraphEngineError("submit_decision() called with no decision pending")
        if response.node_id != self._pending_request.node_id:
            raise ValueError(
                f"Response node_id {response.node_id!r} does not match "
                f"pending request {self._pending_request.node_id!r}"
            )

        checkpoint = self._checkpoint() if self.transactional else None
        node = self.graph.node(self.state.current_node)

        try:
            resolver = get_resolver(node.domain)
            extra = resolver.apply(node, self.state, self.deck, response)  # re-validates internally

            self._pending_request = None
            self._extra = extra or {}
            self._advance_transition(node.id)
            self._run()
        except Exception as exc:
            if checkpoint is not None:
                self._restore(checkpoint)
            raise GraphEngineStepError(
                f"submit_decision() failed while advancing from node "
                f"{node.id!r}: {exc!r}. Engine has been rolled back to "
                f"the state before this call -- pending_request is valid "
                f"again and this decision (or a different one) may be "
                f"retried."
            ) from exc

    def refresh_pending_request(self) -> None:
        """
        Rebuild pending_request for the DECISION node the engine is
        currently sitting at, from the CURRENT state.

        For callers that deliberately modify state AFTER the engine has
        arrived at a decision node (RL scenario setup overriding pot and
        stacks), so the request's option amounts (min/max bet, call
        amount) reflect the modified state. Raises GraphEngineError if the
        engine is not currently at a DECISION node.
        """
        node_id = self.state.current_node
        if node_id is None or self.graph.is_terminal(node_id):
            raise GraphEngineError("refresh_pending_request(): no current decision node")
        node = self.graph.node(node_id)
        if node.kind != NodeKind.DECISION:
            raise GraphEngineError(
                f"refresh_pending_request(): current node {node_id!r} is not a DECISION node"
            )
        resolver = get_resolver(node.domain)
        self._pending_request = resolver.build_request(node, self.state, self.deck)

    # -----------------------------------------------------
    # Checkpoint / restore -- see GraphEngineStepError's docstring
    # -----------------------------------------------------

    def _checkpoint(self) -> Dict[str, Any]:
        return {
            "state": copy.deepcopy(self.state),
            "deck": copy.deepcopy(self.deck),
            "pending_request": self._pending_request,
            "extra": dict(self._extra),
            "last_showdown": self.last_showdown,
            "last_winners": list(self.last_winners) if self.last_winners is not None else None,
            "last_distributed_passes": (
                [dict(d) for d in self.last_distributed_passes]
                if self.last_distributed_passes is not None
                else None
            ),
        }

    def _restore(self, checkpoint: Dict[str, Any]) -> None:
        # Copy every slot value back onto the SAME state/deck objects
        # (never rebind self.state/self.deck themselves) -- callers that
        # already hold a reference to engine.state must see the rollback
        # too, not a stale pre-checkpoint object.
        saved_state = checkpoint["state"]
        for slot in _all_slots(type(self.state)):
            setattr(self.state, slot, getattr(saved_state, slot))

        saved_deck = checkpoint["deck"]
        for slot in _all_slots(type(self.deck)):
            setattr(self.deck, slot, getattr(saved_deck, slot))

        self._pending_request = checkpoint["pending_request"]
        self._extra = checkpoint["extra"]
        self.last_showdown = checkpoint["last_showdown"]
        self.last_winners = checkpoint["last_winners"]
        self.last_distributed_passes = checkpoint["last_distributed_passes"]

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
# unused by most handlers, but kept as a hook rather than something
# bolted on later, since a future mechanic may need it.
# =======================================================================

def _eligible_for_deal(kind: str, state) -> List[int]:
    if kind == "has_stack":
        # A sitting-out seat is never dealt in, regardless of stack --
        # see PlayerState.sitting_out's docstring. Without this check a
        # zero-stack seat would already be excluded by stack > 0, but a
        # seat sitting out with chips still behind (e.g. stepped away)
        # would incorrectly still get dealt cards.
        return [i for i, p in enumerate(state.players) if p.stack > 0 and not p.sitting_out]
    if kind == "active":
        return state.active_players()
    if kind == "remaining":
        return state.remaining_players()
    if kind == "all":
        return [i for i, p in enumerate(state.players) if not p.sitting_out]
    raise ValueError(f"Unknown eligible kind for dealing: {kind!r}")


def _next_eligible_seats(state, start_index: int, count: int) -> List[int]:
    """
    Walk forward from `start_index` (EXCLUSIVE) in seat order, skipping
    any sitting_out seat, and return the next `count` eligible seat
    indices in order.

    Used for blind/ante seat assignment so a sitting-out seat (zero
    stack, or manually sat out) never becomes the small/big blind, and
    -- just as importantly -- never gets silently SKIPPED OVER when
    computing who the real small/big blind is (a naive
    (dealer_position + 1) % n / + 2 % n would land directly on a
    sitting-out seat instead of walking past it to the next real
    player).

    Raises ValueError if fewer than `count` non-sitting-out seats exist
    at all -- that's a table-composition bug the caller needs to know
    about, not something to silently paper over.
    """
    n = len(state.players)
    found: List[int] = []
    idx = start_index
    for _ in range(n):
        idx = (idx + 1) % n
        if not state.players[idx].sitting_out:
            found.append(idx)
            if len(found) == count:
                return found
    raise ValueError(
        f"Could not find {count} eligible (non-sitting-out) seat(s) "
        f"starting after seat {start_index} -- not enough players "
        f"seated this hand"
    )


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
    small_blind = node.config["small_blind"]
    big_blind = node.config["big_blind"]

    sb_idx, bb_idx = _next_eligible_seats(state, state.dealer_position, 2)
    _post_forced_bet(state, sb_idx, small_blind, track_current_bet=True)
    _post_forced_bet(state, bb_idx, big_blind, track_current_bet=True)

    state.bet_to_call = big_blind
    state.min_raise = big_blind

    # Posting the BB is the base-case "last aggressive action" fallback
    # for any persistent-aggressor mechanic (Grinch etc.) -- see
    # GraphGameState.persistent_last_aggressor's docstring. Always wins
    # over whatever handle_post_antes may have set (post_blinds runs
    # after post_antes in every flow that has both -- see standard_graph.py
    # / flow_loader.py step ordering), since blinds being present means
    # the BB IS the designated preflop fallback, not "first to post".
    if big_blind > 0:
        state.record_aggressor(bb_idx)


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
    first_poster = None
    for i in range(len(state.players)):
        if state.players[i].sitting_out:
            continue
        had_stack = state.players[i].stack > 0
        _post_forced_bet(state, i, amount, track_current_bet=True)
        if first_poster is None and had_stack and amount > 0:
            first_poster = i

    # Only meaningful as the persistent-aggressor fallback when this
    # hand has NO blinds at all (a bomb pot) -- handle_post_blinds
    # unconditionally overwrites this with the BB whenever blinds ARE
    # posted, per the documented preflop fallback order (BB beats
    # "first to post an ante").
    if first_poster is not None:
        state.record_aggressor(first_poster)


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
        if not p.has_folded and not p.is_all_in and not p.sitting_out:
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
        if not p.has_folded and not p.sitting_out:
            p.stack += state.pot
            engine.last_showdown = None
            engine.last_winners = [i]
            state.pot = 0
            return
    raise GraphEngineError("award_last_player reached with no remaining (non-folded) players")


def handle_distribute_passes(engine: "GraphEngine", node: Node) -> None:
    decision_node = node.config["decision_node"]
    engine.last_distributed_passes = execute_pending_passes(decision_node, engine.state, engine.deck)


def handle_noop(engine: "GraphEngine", node: Node) -> None:
    return None


AUTO_HANDLERS = {
    "deal": handle_deal,
    "deal_hole_cards": handle_deal_hole_cards,
    "deal_extra_hole_card": handle_deal_extra_hole_card,   # ESG/Catchup ESG/Christmas/Grinch
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