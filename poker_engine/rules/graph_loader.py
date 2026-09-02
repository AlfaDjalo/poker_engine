"""
poker_engine/rules/graph_loader.py

Backward-compatible name for the backend's integration point. All the
actual work now happens in loader.load_game() (which returns the graph
directly, since the graph is no longer a second, optional thing built
from a separate config format -- see loader.py). Kept as a distinct
public name because it's what BACKEND_MIGRATION_PROMPT.md already
documents as the stable entrypoint; no need to churn that call site
again.
"""

from poker_engine.games.loader import load_game as load_game_graph  # noqa: F401