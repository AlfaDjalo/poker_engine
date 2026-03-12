from .base import Constraint
from .types import NodeMask

class ExactlyKConstraint(Constraint):
    """
    Exactly k bits must be set within a given relevant mask.
    """

    __slots__ = ("relevant", "k")

    def __init__(self, relevant: NodeMask, k: int):
        self.relevant = relevant
        self.k = k

    def is_satisfied(self, mask: NodeMask) -> bool:
        return (mask & self.relevant).bit_count() == self.k

class AtLeastKConstraint(Constraint):
    """
    At least k bits must be set within a given relevant mask.
    """
    __slots__ = ("relevant", "k")

    def __init__(self, relevant: NodeMask, k: int):
        self.relevant = relevant
        self.k = k

    def is_satisfied(self, mask: NodeMask) -> bool:
        return (mask & self.relevant).bit_count() >= self.k


class AtMostKConstraint(Constraint):
    """
    At most k bits must be set within a given relevant mask.
    """
    __slots__ = ("relevant", "k")

    def __init__(self, relevant: NodeMask, k: int):
        self.relevant = relevant
        self.k = k

    def is_satisfied(self, mask: NodeMask) -> bool:
        return (mask & self.relevant).bit_count() <= self.k


class ImplicationConstraint(Constraint):
    """
    If all bits in antecedent are present,
    then all bits in consequent must be present.
    """
    __slots__ = ("antecedent", "consequent")

    def __init__(self, antecedent: NodeMask, consequent: NodeMask):
        self.antecedent = antecedent
        self.consequent = consequent

    def is_satisfied(self, mask: NodeMask) -> bool:
        if (mask & self.antecedent) == self.antecedent:
            return (mask & self.consequent) == self.consequent
        return True
    

class MutualExclusionConstraint(Constraint):
    """
    No more than one bit from mask may be set.
    """
    __slots__ = ("relevant",)

    def __init__(self, relevant: NodeMask):
        self.relevant = relevant
    
    def is_satisfied(self, mask: NodeMask) -> bool:
        return (mask & self.relevant).bit_count() <= 1