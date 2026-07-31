from abc import ABC, abstractmethod
from .types import NodeMask

class Constraint(ABC):
    """
    Base constraint class.
    
    A constraint evaluates whether a given bitmask satisfies a rule.
    """

    @abstractmethod
    def is_satisfied(self, mask: NodeMask) -> bool:
        pass