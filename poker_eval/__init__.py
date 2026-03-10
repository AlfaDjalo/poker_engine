"""
Light wrapper around the C++ evaluator.

The compiled extension lives in ``poker_eval._poker_eval``.  If the
extension has not yet been built we expose minimal ``enum`` types and
raise on ``evaluate_hands`` so that imports succeed during development.
"""

from __future__ import annotations

try:
    # when the native module is installed/built in‑place it will be
    # available as a submodule of this package.
    from ._poker_eval import ScoreType, ShowdownType, evaluate_hands  # type: ignore
except ImportError:  # pragma: no cover – build step not done yet
    from enum import Enum

    class ScoreType(Enum):             # fallback for tests
        HIGH = 0
        LOW_27 = 1
        LOW_UNQUAL = 2
        LOW_QUAL = 3
        BADUGI = 4

    class ShowdownType(Enum):          # fallback for tests
        HOLDEM = 0
        OMAHA = 1
        MAKE5 = 2
        DRAW = 3
        BADUGI = 4

    def evaluate_hands(*args, **kwargs):
        raise RuntimeError(
            "poker_eval native extension is not built – "
            "run `pip install -e ./cpp` or `python cpp/setup.py "
            "build_ext --inplace`"
        )

__all__ = ["ScoreType", "ShowdownType", "evaluate_hands"]
