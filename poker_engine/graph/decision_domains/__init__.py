"""
poker_engine/graph/decision_domains/__init__.py

Importing this package registers all five built-in DecisionDomainResolvers
(see base.py's registry) so GraphEngine can find them via
get_resolver(domain) without every caller needing to remember to
register each one by hand. A project adding a genuinely new domain
registers its resolver the same way, typically right after this import.
"""

from poker_engine.graph.decision_domains.base import (
    DecisionDomainResolver,
    get_resolver,
    register_resolver,
)
from poker_engine.graph.decision_domains.betting import BettingResolver
from poker_engine.graph.decision_domains.boolean_choice import BooleanResolver, ChoiceResolver
from poker_engine.graph.decision_domains.card_pass import CardPassResolver, execute_pending_passes
from poker_engine.graph.decision_domains.card_select import CardSelectResolver

register_resolver(BettingResolver())
register_resolver(CardSelectResolver())
register_resolver(CardPassResolver())
register_resolver(BooleanResolver())
register_resolver(ChoiceResolver())