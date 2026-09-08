"""
poker_engine/graph/callbacks.py

Thin, additive integration hooks for callers (backend, logging,
replay, live UI push) that need to observe hand progress -- the
graph-model equivalent of engine_callbacks.EngineCallbacks
(on_hand_start / on_action / on_showdown), adapted to the graph
model's vocabulary.

Deliberately NOT wired into GraphEngine itself. GraphEngine's own step
functions (start(), submit_decision()) stay pure state-machine steps
with no side-channel notification -- these helpers wrap those calls
instead of GraphEngine growing an optional-callbacks constructor
parameter, so:
  - every existing caller of GraphEngine directly (tests, the
    standard_graph/hand_session harness already used to validate the
    engine) keeps working completely unmodified;
  - "does this call fire a callback" is visible at the call site that
    opts in (use hand_session.start_hand/submit_decision instead of
    engine.start()/engine.submit_decision() directly), rather than
    being an invisible property of which constructor arguments were
    passed to GraphEngine three layers up.

Differences from the old EngineCallbacks shape, and why:
  - on_action(state, action, player_index, pot_before, stack_before)
    becomes on_decision(engine, response: DecisionResponse). It covers
    every DecisionDomain (BETTING, CARD_SELECT, CARD_PASS, BOOLEAN,
    CHOICE), not just betting -- a caller that only cares about
    betting actions checks `response.domain == DecisionDomain.BETTING`
    and reads the Action out of `response.value` itself.
    pot_before/stack_before aren't reproduced here: a caller that needs
    a before/after diff can snapshot engine.state before calling
    submit_decision() itself (it already has the engine reference) --
    duplicating that bookkeeping into every callback call was
    PokerState-specific plumbing, not something the hook itself should
    own.
  - on_showdown(state, result) becomes on_showdown(engine, result) --
    engine carries .state, so nothing is lost, and it additionally lets
    a callback read engine.last_winners without recomputing it.
  - on_hand_start(state) becomes on_hand_start(engine): call
    start_hand() (below) in place of engine.start() directly.
  - on_cards_distributed(engine, distributions) is NEW -- fires exactly
    once, right after a CARD_PASS round's distribute_passes AUTO node
    has applied every player's pass simultaneously (see
    decision_domains/card_pass.py). `distributions` is
    engine.last_distributed_passes: a list of
    {"player", "card_ids", "target"} dicts, one per completed pass.
    This is the only point at which a consumer should reveal received
    cards for a pass-the-trash (or any future CARD_PASS) round --
    nothing before this should show a player holding cards they
    haven't actually been dealt yet, regardless of what order the
    Frontend processed each player's *selection* in (see
    CAP_Technical_Quick_Reference.md §3.4: "The Frontend must not
    expect received cards to appear during the decision round").

If engine.start()/engine.submit_decision() raise GraphEngineStepError
(see graph_engine.py), that exception propagates straight out of
start_hand()/submit_decision() below WITHOUT firing any callback --
correct, since a rolled-back call means nothing actually happened.
"""

from typing import Optional

from poker_engine.graph.core_types import DecisionResponse
from poker_engine.graph.graph_engine import GraphEngine


class GraphEngineCallbacks:
    """
    Override whichever hooks a caller needs; every method defaults to a
    no-op, matching engine_callbacks.EngineCallbacks's own shape (a
    plain base class with pass-bodied methods, not an ABC -- a caller
    overriding only on_showdown shouldn't have to stub the other ones).
    """

    def on_hand_start(self, engine: GraphEngine) -> None:
        pass

    def on_decision(self, engine: GraphEngine, response: DecisionResponse) -> None:
        pass

    def on_cards_distributed(self, engine: GraphEngine, distributions) -> None:
        """
        Fires exactly once, right after a CARD_PASS round that just
        completed has had its distribute_passes AUTO node run --
        `distributions` is the list execute_pending_passes() returned:
        [{"player": int, "card_ids": Tuple[int, ...], "target": int}, ...].
        See module docstring for why this is the right/only moment to
        reveal received cards.
        """
        pass

    def on_showdown(self, engine: GraphEngine, result) -> None:
        pass


def start_hand(engine: GraphEngine, callbacks: Optional[GraphEngineCallbacks] = None) -> None:
    """
    Call in place of engine.start() directly when callbacks matter
    (typically via hand_session.start_new_hand, which calls this).

    Fires on_hand_start once the graph has run forward to the first
    DECISION node -- matching PokerState.start_hand()'s own timing:
    after antes/blinds/dealing, right before the first action is ever
    requested (see poker_state.py: on_hand_start fires as the very last
    step of start_hand(), after phase is already set to BETTING).

    Also fires on_cards_distributed/on_showdown if either already
    happened by the time the graph first pauses -- e.g. a hand whose
    very first street is a simultaneous pass-the-trash round with zero
    real decisions before it resolves, or every remaining player
    already all-in the moment the first betting round is entered (see
    standard_graph.py's ActivePlayersCount() == 0 branch, which skips
    straight past a BETTING node with nothing legal to do). In either
    case the event happens inside this very call, and nothing else
    will ever get a chance to fire it.
    """
    engine.start()
    if callbacks:
        callbacks.on_hand_start(engine)
        _maybe_fire_distribution(engine, callbacks)
        _maybe_fire_showdown(engine, callbacks)


def submit_decision(
    engine: GraphEngine,
    response: DecisionResponse,
    callbacks: Optional[GraphEngineCallbacks] = None,
) -> None:
    """
    Call in place of engine.submit_decision(response) directly when
    callbacks matter. Fires on_decision, then on_cards_distributed if
    this decision's round just resolved a CARD_PASS distribution, then
    on_showdown if this decision was the one that completed the hand.
    """
    engine.submit_decision(response)
    if callbacks:
        callbacks.on_decision(engine, response)
        _maybe_fire_distribution(engine, callbacks)
        _maybe_fire_showdown(engine, callbacks)


def _maybe_fire_distribution(engine: GraphEngine, callbacks: GraphEngineCallbacks) -> None:
    if engine.last_distributed_passes is not None:
        callbacks.on_cards_distributed(engine, engine.last_distributed_passes)


def _maybe_fire_showdown(engine: GraphEngine, callbacks: GraphEngineCallbacks) -> None:
    # last_showdown is only ever non-None when a real "showdown" AUTO
    # node ran (see graph_engine.py's handle_showdown) -- never set by
    # handle_award_last_player, matching PokerState._award_last_player's
    # own behaviour of NOT calling on_showdown when the hand ends by
    # everyone-but-one folding (see poker_state.py's two branches).
    if engine.is_complete and engine.last_showdown is not None:
        callbacks.on_showdown(engine, engine.last_showdown)
