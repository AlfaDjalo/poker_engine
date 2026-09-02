"""
poker_engine/graph/decision_domains/boolean_choice.py

BOOLEAN and CHOICE DecisionDomainResolvers.

Both are single-decider, one-shot decisions -- no round/turn-order
machinery needed (contrast BETTING/CARD_SELECT/CARD_PASS, which are all
multi-player rounds). They're grouped in one file because they share
that shape and differ only in what "the answer" looks like: a bool vs.
one label from an enumerated set.

BOOLEAN is what Grinch is built from: a node with decider="last_aggressor",
domain=BOOLEAN records the chosen True/False under a variant-chosen key
(e.g. "christmas_next_street") for a later Transition's
condition.DecisionFlag(...) to read.

decider is NOT restricted to "current_player" here (unlike the round
domains): it's resolved via condition.resolve_decider, which accepts any
of the fixed roles (last_aggressor / dealer / current_player) OR a key
previously recorded in state.decisions holding a player index -- e.g. a
variant that has players elect a "captain" via an earlier CHOICE
decision can point a later BOOLEAN node's decider at that recorded key.

record_key: both resolvers record their outcome under
node.config.get("record_key", node.id) -- defaulting to the node's own
id keeps the common case (one BOOLEAN/CHOICE node, one flag) entirely
config-free, while record_key lets a variant reuse the same logical flag
name across structurally different nodes if it ever needs to.
"""

from poker_engine.graph.condition import resolve_decider
from poker_engine.graph.core_types import (
    BooleanOption,
    ChoiceOption,
    DecisionDomain,
    DecisionRequest,
    DecisionResponse,
)
from poker_engine.graph.decision_domains.base import DecisionDomainResolver
from poker_engine.graph.node import Node


class BooleanResolver(DecisionDomainResolver):

    domain = DecisionDomain.BOOLEAN

    def build_request(self, node: Node, state, deck) -> DecisionRequest:
        player = resolve_decider(node.decider, state)
        option = BooleanOption(label=node.config.get("label", "confirm"))
        return DecisionRequest(node_id=node.id, domain=self.domain, player_index=player, options=(option,))

    def validate(self, node: Node, state, deck, response: DecisionResponse) -> None:
        super().validate(node, state, deck, response)
        if not isinstance(response.value, bool):
            raise ValueError(f"BOOLEAN response.value must be a bool, got {type(response.value)!r}")

    def apply(self, node: Node, state, deck, response: DecisionResponse) -> None:
        self.validate(node, state, deck, response)
        key = node.config.get("record_key", node.id)
        state.record_decision(key, response.value)


class ChoiceResolver(DecisionDomainResolver):

    domain = DecisionDomain.CHOICE

    def build_request(self, node: Node, state, deck) -> DecisionRequest:
        player = resolve_decider(node.decider, state)
        option = ChoiceOption(labels=tuple(node.config["labels"]))
        return DecisionRequest(node_id=node.id, domain=self.domain, player_index=player, options=(option,))

    def validate(self, node: Node, state, deck, response: DecisionResponse) -> None:
        super().validate(node, state, deck, response)
        request = self.build_request(node, state, deck)
        labels = request.options[0].labels
        if response.value not in labels:
            raise ValueError(f"{response.value!r} is not a legal choice; options are {labels}")

    def apply(self, node: Node, state, deck, response: DecisionResponse) -> None:
        self.validate(node, state, deck, response)
        key = node.config.get("record_key", node.id)
        state.record_decision(key, response.value)