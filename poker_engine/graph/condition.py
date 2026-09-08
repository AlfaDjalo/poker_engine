"""
poker_engine/graph/condition.py

Small, closed condition-expression grammar used to guard Transitions.

Deliberately NOT a general expression language: conditions are built out
of a fixed, typed set of Accessors (each reads one specific piece of
game/graph state) plus comparisons and boolean combinators over them.
This is a direct design choice against "the graph shouldn't become a
collection of special-case poker rules": ESG, Catchup ESG, Christmas, and
Grinch are each just an accessor-and-comparison, or a DecisionFlag check
-- not new engine code. If a future mechanic genuinely needs a state fact
no existing Accessor exposes, that's ONE new Accessor subclass (a single
well-named read), never a bespoke Condition.

ConditionContext carries state + deck + a small `extra` scratch dict.
`extra` is populated by the node handler immediately before it evaluates
a node's outgoing transitions, for structural facts that are local to
"the operation about to run" rather than persistent game state -- e.g.
Christmas needs "how many board cards does the upcoming DEAL node still
need to fill", which is a fact about graph config, not something worth
persisting on GameState itself.

`state.decisions` (a persistent Dict[str, Any] recording resolved
DECISION outcomes across the whole hand -- e.g. Grinch's "christmas next
street?" answer) is expected to exist on whatever state object is passed
in; it's added when GameState is extended for graph play (see
graph_state.py), not created here.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class ConditionContext:
    """Everything a Condition might need. Built fresh by the GraphEngine
    each time it evaluates a node's outgoing transitions."""

    state: Any    # poker_engine.state.game_state.GameState (untyped to avoid an import cycle)
    deck: Any     # poker_engine.cards.deck.Deck
    extra: Dict[str, Any] = field(default_factory=dict)


class Accessor(ABC):
    """Reads one specific, named value out of a ConditionContext."""

    @abstractmethod
    def get(self, ctx: ConditionContext) -> Any:
        ...

    def __repr__(self):
        return self.__class__.__name__


class Condition(ABC):
    """A boolean guard on a Transition."""

    @abstractmethod
    def evaluate(self, ctx: ConditionContext) -> bool:
        ...


# ---------------------------------------------------------------------
# Built-in accessors
# ---------------------------------------------------------------------

class Constant(Accessor):
    def __init__(self, value: Any):
        self.value = value

    def get(self, ctx):
        return self.value

    def __repr__(self):
        return f"Constant({self.value!r})"


class DiscardPileCount(Accessor):
    """Cards currently sitting in the discard pile -- drives ESG."""

    def get(self, ctx):
        return len(ctx.state.discard_pile)


class DeckRemainingCount(Accessor):
    """Cards left undrawn in the deck -- drives Christmas."""

    def get(self, ctx):
        from poker_engine.cards.mask import mask_to_card_ids
        return sum(1 for _ in mask_to_card_ids(ctx.deck.remaining_mask()))


class PlayersRemainingCount(Accessor):
    """Players still in the hand (not folded)."""

    def get(self, ctx):
        return len(ctx.state.remaining_players())


class ActivePlayersCount(Accessor):
    """Players who can still act (not folded, not all-in)."""

    def get(self, ctx):
        return len(ctx.state.active_players())


class ActivePlayers(Accessor):
    """Player indices who can still act (not folded, not all-in)."""

    def get(self, ctx):
        return ctx.state.active_players()


class RemainingPlayers(Accessor):
    """Player indices still in the hand (not folded), including all-in ones."""

    def get(self, ctx):
        return ctx.state.remaining_players()


class Sum(Accessor):
    """
    Adds together several resolved values -- each term may be an Accessor
    or a plain literal. Exists specifically so mechanics like Christmas
    (deck_remaining >= board_cards_needed + players_remaining) don't need
    a runtime "extra context" mechanism: board_cards_needed is a
    compile-time-known constant for a given DEAL node (the variant author
    knows the flop deals 3 cards), so it's just Constant(3) --
    Sum(Constant(3), PlayersRemainingCount()) is the whole right-hand side.
    """

    def __init__(self, *terms):
        self.terms = terms

    def get(self, ctx):
        return sum(t.get(ctx) if isinstance(t, Accessor) else t for t in self.terms)

    def __repr__(self):
        return f"Sum({', '.join(map(repr, self.terms))})"


class DecisionFlag(Accessor):
    """
    Reads a previously-recorded decision outcome by key -- e.g. the
    boolean result of a Grinch "trigger Christmas?" decision. Set by the
    DECISION node handler when it applies a DecisionResponse (see
    graph_engine.py). Returns `default` if the key hasn't been set yet
    (e.g. before the relevant decision has ever occurred in this hand).
    """

    def __init__(self, key: str, default: Any = None):
        self.key = key
        self.default = default

    def get(self, ctx):
        return ctx.state.decisions.get(self.key, self.default)

    def __repr__(self):
        return f"DecisionFlag({self.key!r})"


class ExtraValue(Accessor):
    """
    Reads a transient, node-local value the current node handler stashed
    in ctx.extra right before evaluating transitions (see module
    docstring). Returns `default` if absent.
    """

    def __init__(self, key: str, default: Any = None):
        self.key = key
        self.default = default

    def get(self, ctx):
        return ctx.extra.get(self.key, self.default)

    def __repr__(self):
        return f"ExtraValue({self.key!r})"


PLAYER_ROLE_FIELDS = {
    "last_aggressor": "last_aggressor",
    # Generic, cross-street "last aggressor" fallback chain -- see
    # GraphGameState.persistent_last_aggressor's own docstring for why
    # this is a distinct role from plain "last_aggressor" (which is
    # reset every street by reset_betting_round() and goes None on a
    # check-through street). Grinch is the first consumer; deliberately
    # not named/scoped to Grinch specifically.
    "persistent_last_aggressor": "persistent_last_aggressor",
    "dealer": "dealer_position",
    "current_player": "current_player",
}


def resolve_decider(decider: str, state) -> int:
    """
    Resolve a Node.decider string to a concrete player index. Shared by
    any DECISION resolver whose decider isn't hardcoded to
    "current_player" (see decision_domains/boolean_choice.py).

    Accepts either one of the fixed PLAYER_ROLE_FIELDS roles, or a key
    previously recorded in state.decisions holding a player index --
    e.g. a variant that elects a "captain" via an earlier CHOICE
    decision can point a later node's decider at that recorded key.
    """
    if decider in PLAYER_ROLE_FIELDS:
        value = getattr(state, PLAYER_ROLE_FIELDS[decider])
        if value is None:
            raise ValueError(
                f"Role {decider!r} has no resolved player yet "
                f"(state.{PLAYER_ROLE_FIELDS[decider]} is None)"
            )
        return value

    if decider in state.decisions:
        value = state.decisions[decider]
        if not isinstance(value, int):
            raise ValueError(f"state.decisions[{decider!r}] is not a player index: {value!r}")
        return value

    raise ValueError(
        f"Cannot resolve decider {decider!r}: not a known role "
        f"({sorted(PLAYER_ROLE_FIELDS)}) and not found in state.decisions"
    )


class CurrentPlayerIs(Accessor):
    """
    Resolves a named player role to a player index, for comparison
    against ctx.state.current_player (e.g. Grinch: 
    Compare(CurrentPlayerIs("last_aggressor"), "==", CurrentPlayerIs("current_player"))).
    Thin wrapper around resolve_decider so Condition and Node.decider
    resolution share exactly one role table.
    """

    def __init__(self, role: str):
        if role not in PLAYER_ROLE_FIELDS:
            raise ValueError(f"Unknown player role: {role!r}")
        self.role = role

    def get(self, ctx) -> int:
        return resolve_decider(self.role, ctx.state)

    def __repr__(self):
        return f"CurrentPlayerIs({self.role!r})"


# ---------------------------------------------------------------------
# Comparisons
# ---------------------------------------------------------------------

class Compare(Condition):
    """
    left <op> right, where left/right may each be an Accessor or a plain
    literal. Supported ops: "==", "!=", "<", "<=", ">", ">=", "in".
    """

    _OPS = {
        "==": lambda a, b: a == b,
        "!=": lambda a, b: a != b,
        "<": lambda a, b: a < b,
        "<=": lambda a, b: a <= b,
        ">": lambda a, b: a > b,
        ">=": lambda a, b: a >= b,
        "in": lambda a, b: a in b,
    }

    def __init__(self, left, op: str, right):
        if op not in self._OPS:
            raise ValueError(f"Unsupported comparison operator: {op!r}")
        self.left = left
        self.op = op
        self.right = right

    @staticmethod
    def _resolve(value, ctx):
        return value.get(ctx) if isinstance(value, Accessor) else value

    def evaluate(self, ctx: ConditionContext) -> bool:
        left = self._resolve(self.left, ctx)
        right = self._resolve(self.right, ctx)
        return self._OPS[self.op](left, right)

    def __repr__(self):
        return f"Compare({self.left!r} {self.op} {self.right!r})"


# ---------------------------------------------------------------------
# Boolean combinators
# ---------------------------------------------------------------------

class And(Condition):
    def __init__(self, *conditions: Condition):
        self.conditions = conditions

    def evaluate(self, ctx):
        return all(c.evaluate(ctx) for c in self.conditions)

    def __repr__(self):
        return f"And({', '.join(map(repr, self.conditions))})"


class Or(Condition):
    def __init__(self, *conditions: Condition):
        self.conditions = conditions

    def evaluate(self, ctx):
        return any(c.evaluate(ctx) for c in self.conditions)

    def __repr__(self):
        return f"Or({', '.join(map(repr, self.conditions))})"


class Not(Condition):
    def __init__(self, condition: Condition):
        self.condition = condition

    def evaluate(self, ctx):
        return not self.condition.evaluate(ctx)

    def __repr__(self):
        return f"Not({self.condition!r})"


class Always(Condition):
    """Unconditional -- the default/fallback transition guard."""

    def evaluate(self, ctx):
        return True

    def __repr__(self):
        return "Always()"


# ---------------------------------------------------------------------
# Round-completion conditions
#
# A DECISION node representing a multi-player round (a betting round, a
# discard round, ...) is modeled as a node with a self-loop transition
# ("still players left to act -> come back to this same node") and a
# forward transition ("round complete -> move on"). These two Condition
# classes are what the forward transition checks; the self-loop is just
# Not(...) of the same condition (or, more simply, listed after it with
# Always() as GameGraph requires every node's transition list to end
# unconditionally -- see game_graph.py).
# ---------------------------------------------------------------------

class BettingRoundComplete(Condition):
    """
    True once the current betting round is complete.

    Reads ctx.extra["betting_round_complete"] -- a snapshot taken by
    BettingResolver.apply() at the moment an action was applied, BEFORE
    current_player was potentially advanced -- rather than calling
    ctx.state.betting_round_complete() live. Live re-evaluation would be
    wrong here: GameState's own betting_round_complete() is a "has the
    turn cycled all the way back to last_to_act" check that's only valid
    checked once, immediately after the action that was just applied; if
    re-checked after advance_turn() has already moved current_player,
    it gives a false positive the instant current_player first cycles
    around to equal last_to_act, even though that player hasn't acted
    yet this round. See BettingResolver.apply()'s docstring.

    Only meaningful as (part of) the outgoing-transition guard on the
    same BET node whose apply() just ran -- using it anywhere else will
    raise a KeyError, which is the correct failure mode: it means this
    condition was used somewhere the snapshot was never taken.
    """

    def evaluate(self, ctx: ConditionContext) -> bool:
        return ctx.extra["betting_round_complete"]

    def __repr__(self):
        return "BettingRoundComplete()"


class RoundComplete(Condition):
    """
    True once every player in `eligible` (an Accessor returning a list of
    player indices, typically ActivePlayers() or RemainingPlayers()) has
    been recorded in state.round_acted for the current node. Used for any
    non-betting multi-player round (a discard round, a pass-the-trash
    round, ...) -- see graph_state.GraphGameState.round_acted.
    """

    def __init__(self, eligible: Accessor):
        self.eligible = eligible

    def evaluate(self, ctx: ConditionContext) -> bool:
        eligible_players = self.eligible.get(ctx)
        return all(ctx.state.has_acted(p) for p in eligible_players)

    def __repr__(self):
        return f"RoundComplete(eligible={self.eligible!r})"
