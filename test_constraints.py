from constraints.types import bit
from constraints.engine import ConstraintEngine
from constraints.builtin import ExactlyKConstraint

A = bit(0)
B = bit(1)
C = bit(2)

engine = ConstraintEngine()
engine.add(ExactlyKConstraint(A | B | C, 2))

mask = A | B

print(engine.validate(mask))