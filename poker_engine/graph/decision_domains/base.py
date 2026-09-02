"""
poker_engine/graph/decision_domains/base.py

DecisionDomainResolver: the common interface every DecisionDomain
implements. GraphEngine never contains domain-specific logic itself -- it
only ever calls resolver.build_request(...) to find out what's legal at
a DECISION node, and resolver.apply(...) to carry out an already-validated
DecisionResponse. This is what makes adding a brand-new decision domain
(something beyond the current BETTING / CARD_SELECT / CARD_PASS /
BOOLEAN / CHOICE set) additive rather than invasive: implement one
resolver, register it, done -- GraphEngine, GameGraph, and every existing
resolver stay untouched.

The registry is a plain dict rather than e.g. an entry-point/plugin
system, since the domain set is small and known at import time; nothing
here prevents a project from registering additional custom domains at
startup if a future mechanic genuinely doesn't fit the existing five.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from poker_engine.graph.core_types import DecisionDomain, DecisionRequest, DecisionResponse
from poker_engine.graph.node import Node


class DecisionDomainResolver(ABC):
    """
    One resolver per DecisionDomain. Stateless -- takes node/state/deck
    as arguments rather than holding its own references, so a single
    resolver instance serves every node of its domain, across every
    variant and every hand.
    """

    domain: DecisionDomain

    @abstractmethod
    def build_request(self, node: Node, state, deck) -> DecisionRequest:
        """
        Return the DecisionRequest currently on offer at `node`, given
        live state. Called fresh every time the engine needs to know
        what's legal -- e.g. after each self-loop back to a multi-player
        round node, the request reflects the NEW current player /
        remaining eligible set, never a cached one from the node's first
        visit.
        """
        ...

    @abstractmethod
    def apply(self, node: Node, state, deck, response: DecisionResponse) -> Optional[Dict[str, Any]]:
        """
        Apply an already-validated DecisionResponse: mutate state (via
        CardMoveExecutor for anything that moves cards, state.apply_action
        for betting, state.record_decision(...) for anything a later
        Condition might need to read) and update state.round_acted /
        advance turn order as appropriate for this domain.

        May return a dict, which GraphEngine merges into the
        ConditionContext.extra used to evaluate THIS node's own outgoing
        transitions immediately afterward -- for any fact that needs to
        be captured at the moment of applying the decision, before any
        state mutation the resolver itself performs (e.g. advancing
        current_player) could make a live re-read of that fact wrong.
        BettingResolver uses this: whether the round completed must be
        judged as of the action just applied, not re-derived after
        current_player has possibly already moved on (see betting.py).
        Most domains don't need this and simply return None.

        Does NOT decide graph transitions itself -- that's GraphEngine's
        job, evaluating Conditions once apply() returns.
        """
        ...

    def validate(self, node: Node, state, deck, response: DecisionResponse) -> None:
        """
        Raise ValueError if `response` isn't a legal answer to the
        CURRENT build_request(node, state, deck) -- a response is never
        trusted against a stale/previous request. The default
        implementation re-derives the current request and checks
        identity/player fields; subclasses layer their own
        option-legality check on top (typically by overriding this and
        calling super().validate(...) first).
        """
        request = self.build_request(node, state, deck)
        if response.domain != self.domain:
            raise ValueError(f"Response domain {response.domain} != resolver domain {self.domain}")
        if response.node_id != node.id:
            raise ValueError(f"Response node_id {response.node_id!r} != current node {node.id!r}")
        if response.player_index != request.player_index:
            raise ValueError(
                f"Response player_index {response.player_index} != "
                f"expected decider {request.player_index}"
            )


_REGISTRY: Dict[DecisionDomain, DecisionDomainResolver] = {}


def register_resolver(resolver: DecisionDomainResolver) -> None:
    _REGISTRY[resolver.domain] = resolver


def get_resolver(domain: DecisionDomain) -> DecisionDomainResolver:
    try:
        return _REGISTRY[domain]
    except KeyError:
        raise ValueError(f"No DecisionDomainResolver registered for {domain}") from None