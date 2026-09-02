"""
poker_engine/graph/hand_session.py

start_new_hand(...): the graph-model's equivalent of the per-hand
lifecycle bookkeeping PokerState.start_hand() used to do BEFORE handing
off to its Phase state machine -- resetting node_cards/discard_pile,
resetting player-per-hand fields, shuffling the deck, advancing the
dealer button -- then hands off to GraphEngine.start().

Why this isn't a graph AUTO node
---------------------------------
Every AUTO handler in graph_engine.py's AUTO_HANDLERS is deliberately
generic: it reads whatever it needs from `node.config`, never from a
GameDefinition. node_cards needs to be sized to `node_count`, which is a
per-variant fact that lives on GameDefinition, not on any Node -- an
AUTO node would have to either hardcode a count (defeating the point of
one shared "setup" node id across every variant) or have the loader
thread node_count into every "setup" node's config as a special case
just for this one field. Doing the sizing once, here, in the thin layer
that already has both game_def and state in hand, avoids inventing that
extra plumbing.

This module is a convenience, not a required part of the architecture:
anything that constructs its own GraphGameState/Deck is free to do this
setup itself (see this function's body -- there's nothing here a caller
couldn't inline) and call GraphEngine.start() directly.
"""

from typing import List, Optional

from poker_engine.graph.callbacks import GraphEngineCallbacks
from poker_engine.graph.callbacks import start_hand as _fire_start_hand
from poker_engine.graph.graph_engine import GraphEngine
from poker_engine.graph.graph_state import GraphGameState
from poker_engine.state.player_state import PlayerState


def start_new_hand(
    engine: GraphEngine,
    game_def,
    advance_dealer: bool = True,
    callbacks: Optional[GraphEngineCallbacks] = None,
) -> None:
    """
    Reset `engine.state`/`engine.deck` for a new hand of `game_def` and
    run the graph forward to the first DECISION node (or straight to
    completion, for a graph with no decisions at all).

    Mirrors PokerState.start_hand()'s pre-graph bookkeeping:
      - node_cards reset to [None] * game_def.node_count
      - discard_pile cleared
      - each player's per-hand fields reset (current_bet,
        total_contribution, has_folded, is_all_in, hand_mask) -- stack
        is deliberately left untouched, it carries over between hands
      - dealer_position advanced one seat (skip via advance_dealer=False
        for the very first hand of a session, matching PokerState's own
        dealer_position starting at 0 with the first start_hand() call
        already advancing it to 1 -- callers that want hand 1 dealt from
        seat 0 should pass advance_dealer=False for that one call)
      - deck reshuffled

    Does NOT post blinds/antes or deal any cards itself -- those are
    ordinary AUTO nodes (post_blinds/post_antes/deal_hole_cards/deal)
    reached by walking the graph from its entry_node, exactly like every
    other AUTO node. This function only does the bookkeeping no node in
    the graph is positioned to do generically (see module docstring).

    `callbacks`, if given, is passed straight to callbacks.start_hand()
    -- see callbacks.py for on_hand_start/on_showdown firing semantics.
    Use callbacks.submit_decision(engine, response, callbacks) in place
    of engine.submit_decision(response) for every subsequent decision in
    the hand, to keep on_decision/on_showdown firing consistently.
    """
    state = engine.state
    assert isinstance(state, GraphGameState), (
        "start_new_hand requires a GraphGameState (for current_node/"
        "decisions/round_acted) -- got a plain GameState"
    )

    if advance_dealer:
        state.dealer_position = (state.dealer_position + 1) % len(state.players)

    state.pot = 0
    state.node_cards = [None] * game_def.node_count
    state.discard_pile = []
    state.decisions = {}
    state.round_acted = set()

    for p in state.players:
        p.current_bet = 0
        p.total_contribution = 0
        p.has_folded = False
        p.is_all_in = False
        p.hand_mask = 0

    engine.deck.shuffle()

    engine.last_showdown = None
    engine.last_winners = None

    _fire_start_hand(engine, callbacks)


def new_hand_state(players: List[PlayerState], game_def, dealer_position: int = 0) -> GraphGameState:
    """
    Convenience constructor for the GraphGameState start_new_hand()
    expects, when a caller doesn't already have one (e.g. the first hand
    of a fresh session). Pass advance_dealer=False to the following
    start_new_hand() call if `dealer_position` should be used as-is
    rather than advanced first.
    """
    state = GraphGameState(players, betting_type="no_limit")  # vestigial: only read by GameState's
    # pre-graph legal_actions()/apply_action() branching, which the graph
    # engine never calls -- see graph_state.py's own docstring note on
    # this becoming dead code once the graph is the sole execution path.
    # Each betting step now picks its own BettingRules directly in the
    # flow YAML (see flow_loader.py), so there is no single game-level
    # "betting_type" left to read off GameDefinition.
    state.dealer_position = dealer_position
    return state