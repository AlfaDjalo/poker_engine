"""
poker_engine/graph/graph_state.py

GraphGameState extends the existing GameState with the two pieces of
per-hand data the graph model needs on top of it:

  - current_node: which Node the hand is currently sitting at. This is
    the single fact that drives everything an AI/UI needs to know --
    combined with GameGraph, it's how the engine derives whose turn it
    is, what kind of decision (if any) is pending, and what's legal.

  - decisions: a persistent record of resolved DECISION outcomes for
    this hand, keyed by a caller-chosen string (e.g. "grinch_christmas",
    "pass_target_player_2"). This is what condition.DecisionFlag reads,
    and it's the natural place to look when reasoning about "what
    already happened this hand" without inventing a bespoke state field
    for every new mechanic.

This is deliberately a THIN extension. Everything that already existed
(players, node_cards, pot, discard_pile, betting fields, etc.) is
untouched -- GraphGameState IS-A GameState, not a rewrite of one.
Subclassing (rather than composition) keeps every existing GameState
method (apply_action, legal_actions, build_side_pots,
betting_round_complete, advance_turn, ...) directly usable by the graph
engine with no adapter layer.

Note on migration: GameState.legal_actions()/apply_action() contain
betting-type branching (no_limit/pot_limit/push_fold/river_only) that
predates the graph model and duplicates
poker_engine.actions.betting_rules.BettingRules. The graph engine's
BETTING decision resolver (decision_domains/betting.py) calls into
BettingRules directly instead of GameState.legal_actions() -- that
inline branching becomes dead code once the graph engine is the only
execution path, and should be deleted then. It's left alone here since
PokerState (the pre-graph orchestrator) still depends on it during the
migration window.
"""

from typing import Any, Dict, List, Optional

from poker_engine.state.game_state import GameState
from poker_engine.state.player_state import PlayerState


class GraphGameState(GameState):

    __slots__ = ("current_node", "decisions", "round_acted")

    def __init__(self, players: List[PlayerState], betting_type: str = "no_limit"):
        super().__init__(players, betting_type=betting_type)
        self.current_node: Optional[str] = None
        self.decisions: Dict[str, Any] = {}

        # Generic multi-player round tracking, for DECISION domains other
        # than BETTING (which already has its own mature round-completion
        # machinery -- players_acted/bet_to_call/last_to_act via
        # betting_round_complete() -- reused as-is rather than duplicated).
        # A CARD_SELECT discard round, for instance, reuses current_player
        # + advance_turn() to drive turn order exactly like betting does,
        # but tracks completion via round_acted instead of bet amounts:
        # each player's resolver call adds itself here, and a node's
        # "everyone's decided" transition condition compares round_acted
        # against the domain's eligible-player set (see condition.RoundComplete).
        self.round_acted: set = set()

    def record_decision(self, key: str, value: Any) -> None:
        """
        Record a resolved DECISION outcome under `key`, for later
        DecisionFlag(key) reads. Overwrites any prior value for the same
        key -- callers that need history rather than "latest value" (a
        variant tracking every Pass-the-Trash round across streets, say)
        should namespace their own keys, e.g. f"pass_trash_{street_index}".
        """
        self.decisions[key] = value

    def begin_round(self) -> None:
        """
        Reset round-tracking. Triggered by a "begin_decision_round" AUTO
        node (see graph_engine.py's AUTO_HANDLERS), which a variant's
        graph places immediately before a round's first DECISION node --
        never called automatically by the engine on some inferred
        "fresh vs self-loop" heuristic, since that would mean special-
        casing DECISION nodes inside the core transition loop. This way
        the engine's transition-advance logic stays domain-agnostic: it
        always just runs whatever AUTO node is next, including this one.
        """
        self.round_acted = set()

    def mark_acted(self, player_index: int) -> None:
        self.round_acted.add(player_index)

    def has_acted(self, player_index: int) -> bool:
        return player_index in self.round_acted