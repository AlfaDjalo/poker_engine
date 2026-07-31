from typing import Iterable, List
from .types import NodeMask
from .base import Constraint


class ConstraintEngine:
    """
    Holds a set of constraints and validates masks.
    """

    __slots__ = ("_constraints",)

    def __init__(self, constraints: Iterable[Constraint] | None = None):
        self._constraints: List[Constraint] = list(constraints) if constraints else []

    def add(self, constraint: Constraint) -> None:
        self._constraints.append(constraint)

    def validate(self, mask: NodeMask) -> bool:
        for constraint in self._constraints:
            if not constraint.is_satisfied(mask):
                return False
        return True
    
    def validate_or_raise(self, mask: NodeMask) -> None:
        for constraint in self._constraints:
            if not constraint.is_satisfied(mask):
                raise ValueError(f"Constraint violated: {constraint}")
    
